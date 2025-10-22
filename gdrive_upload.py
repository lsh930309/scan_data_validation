#!/usr/bin/env python3
"""
Google Drive 업로드 스크립트
.gitignore에 등록된 대용량 파일/폴더를 Google Drive에 백업합니다.
"""

import os
import sys
import json
import pickle
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from tqdm import tqdm

# OAuth 2.0 권한 범위
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# 업로드할 항목 목록
SYNC_ITEMS = [
    'images',
    'csv',
    'handout',
    'EXTRACT',
    'value_masters-v5',
    'data.json',
    'data.json.bak',
    'data_v3.jsonc',
]

# Google Drive 루트 폴더 이름
DRIVE_ROOT_FOLDER = 'scan_data_validation_backup'

# 멀티스레딩 설정
MAX_WORKERS = 50  # 동시 업로드 스레드 수 (조정 가능)


class GDriveUploader:
    """Google Drive 업로드 관리자"""

    def __init__(self, project_root: Path, max_workers: int = MAX_WORKERS):
        self.project_root = project_root
        self.credentials_file = project_root / 'credentials.json'
        self.token_file = project_root / 'token.json'
        self.service = None
        self.root_folder_id = None
        self.max_workers = max_workers
        self.upload_lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.uploaded_count = 0
        self.failed_count = 0
        self.creds = None  # 인증 정보 저장

    def authenticate(self):
        """Google Drive API 인증"""
        creds = None

        # 기존 토큰 로드
        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        # 토큰이 없거나 만료된 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("토큰 갱신 중...")
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    print(f"❌ {self.credentials_file} 파일이 없습니다.")
                    print("GDRIVE_SETUP.md 문서를 참고하여 OAuth 인증 파일을 생성하세요.")
                    sys.exit(1)

                print("브라우저에서 Google 계정 인증을 진행합니다...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # 토큰 저장
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
            print("✅ 인증 완료")

        self.creds = creds  # 인증 정보 저장
        self.service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive API 연결 완료")

    def _get_service(self):
        """스레드 안전 서비스 객체 생성"""
        # 각 스레드마다 독립적인 서비스 객체 생성
        return build('drive', 'v3', credentials=self.creds)

    def get_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """폴더 가져오기 또는 생성"""
        # 기존 폴더 검색
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        try:
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = results.get('files', [])
            if files:
                return files[0]['id']

            # 폴더 생성
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                file_metadata['parents'] = [parent_id]

            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()

            return folder.get('id')

        except HttpError as error:
            print(f"❌ 폴더 생성/조회 실패: {error}")
            raise

    def upload_file(self, local_path: Path, parent_id: str, file_name: Optional[str] = None) -> str:
        """파일 업로드"""
        if not file_name:
            file_name = local_path.name

        # 기존 파일 검색
        query = f"name='{file_name}' and '{parent_id}' in parents and trashed=false"
        results = self.service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        files = results.get('files', [])

        file_metadata = {'name': file_name, 'parents': [parent_id]}
        media = MediaFileUpload(str(local_path), resumable=True)

        try:
            if files:
                # 기존 파일 업데이트
                file_id = files[0]['id']
                file = self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
            else:
                # 새 파일 생성
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

            return file.get('id')

        except HttpError as error:
            print(f"❌ 파일 업로드 실패 ({local_path}): {error}")
            raise

    def _upload_file_thread_safe(self, file_path: Path, parent_folder_id: str):
        """스레드 안전 파일 업로드"""
        # 각 스레드마다 독립적인 서비스 객체 사용
        service = self._get_service()
        file_name = file_path.name

        # 기존 파일 검색
        query = f"name='{file_name}' and '{parent_folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)'
        ).execute()

        files = results.get('files', [])
        file_metadata = {'name': file_name, 'parents': [parent_folder_id]}
        media = MediaFileUpload(str(file_path), resumable=True)

        if files:
            # 기존 파일 업데이트
            file_id = files[0]['id']
            service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
        else:
            # 새 파일 생성
            service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

    def _upload_file_worker(self, file_path: Path, parent_folder_id: str, local_dir: Path, total_files: int):
        """멀티스레딩 업로드 워커"""
        try:
            self._upload_file_thread_safe(file_path, parent_folder_id)
            with self.stats_lock:
                self.uploaded_count += 1
                relative_path = file_path.relative_to(local_dir)
                print(f"   [{self.uploaded_count}/{total_files}] ✓ {relative_path}")
            return True
        except Exception as e:
            with self.stats_lock:
                self.failed_count += 1
                relative_path = file_path.relative_to(local_dir)
                print(f"   ❌ {relative_path}: {e}")
            return False

    def upload_directory(self, local_dir: Path, parent_id: str, desc: str = ""):
        """디렉토리 재귀 업로드 (멀티스레딩)"""
        if not local_dir.exists():
            print(f"⚠️  {local_dir} 폴더가 존재하지 않습니다. 건너뜁니다.")
            return

        # 폴더 생성
        folder_id = self.get_or_create_folder(local_dir.name, parent_id)

        # 파일 목록 수집
        files = []
        dirs = []
        for item in local_dir.rglob('*'):
            if item.is_file():
                files.append(item)
            elif item.is_dir():
                dirs.append(item)

        print(f"📁 {local_dir.name}: 파일 {len(files)}개, 폴더 {len(dirs)}개")

        # 폴더 구조 생성 (순차 처리)
        print(f"   폴더 구조 생성 중...")
        folder_map = {local_dir: folder_id}
        for dir_path in sorted(dirs):
            relative_path = dir_path.relative_to(local_dir)
            parent_path = local_dir / relative_path.parent
            parent_folder_id = folder_map[parent_path]

            new_folder_id = self.get_or_create_folder(dir_path.name, parent_folder_id)
            folder_map[dir_path] = new_folder_id

        # 파일 업로드 (멀티스레딩)
        print(f"   파일 업로드 시작... (동시 {self.max_workers}개 스레드)")
        self.uploaded_count = 0
        self.failed_count = 0

        # ThreadPoolExecutor로 병렬 업로드
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for file_path in files:
                parent_folder_id = folder_map[file_path.parent]
                future = executor.submit(
                    self._upload_file_worker,
                    file_path,
                    parent_folder_id,
                    local_dir,
                    len(files)
                )
                futures.append(future)

            # 모든 작업 완료 대기
            for future in as_completed(futures):
                future.result()

        print(f"\n   ✅ {local_dir.name} 업로드 완료!")
        print(f"      성공: {self.uploaded_count}개, 실패: {self.failed_count}개")

    def upload_single_file(self, local_file: Path, parent_id: str, desc: str = ""):
        """단일 파일 업로드"""
        if not local_file.exists():
            print(f"⚠️  {local_file} 파일이 존재하지 않습니다. 건너뜁니다.")
            return

        print(f"📄 {local_file.name} ({local_file.stat().st_size / 1024 / 1024:.2f} MB)")
        try:
            self.upload_file(local_file, parent_id, local_file.name)
            print(f"✅ {local_file.name} 업로드 완료")
        except Exception as e:
            print(f"❌ {local_file.name} 업로드 실패: {e}")

    def sync(self, items: Optional[List[str]] = None):
        """동기화 실행"""
        print(f"\n{'='*60}")
        print(f"Google Drive 업로드 시작")
        print(f"프로젝트: {self.project_root}")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # 인증
        self.authenticate()

        # 루트 폴더 생성/조회
        print(f"📁 루트 폴더 확인: {DRIVE_ROOT_FOLDER}")
        self.root_folder_id = self.get_or_create_folder(DRIVE_ROOT_FOLDER)
        print(f"✅ 폴더 ID: {self.root_folder_id}\n")

        # 업로드할 항목 결정
        sync_items = items if items else SYNC_ITEMS

        # 항목별 업로드
        for item_name in sync_items:
            item_path = self.project_root / item_name

            if item_path.is_dir():
                self.upload_directory(item_path, self.root_folder_id)
            elif item_path.is_file():
                self.upload_single_file(item_path, self.root_folder_id)
            else:
                print(f"⚠️  {item_name}이(가) 존재하지 않습니다. 건너뜁니다.")

            print()

        print(f"\n{'='*60}")
        print(f"✅ 모든 업로드 완료!")
        print(f"Google Drive 폴더: {DRIVE_ROOT_FOLDER}")
        print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Google Drive에 프로젝트 데이터 업로드',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 업로드
  python gdrive_upload.py

  # 특정 항목만 업로드
  python gdrive_upload.py --only images csv data.json

  # .venv 제외하고 업로드
  python gdrive_upload.py --exclude .venv
        """
    )

    parser.add_argument(
        '--only',
        nargs='+',
        metavar='ITEM',
        help='특정 항목만 업로드 (예: images csv)'
    )

    parser.add_argument(
        '--exclude',
        nargs='+',
        metavar='ITEM',
        help='특정 항목 제외 (예: .venv)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=MAX_WORKERS,
        metavar='N',
        help=f'동시 업로드 스레드 수 (기본: {MAX_WORKERS}, 권장: 5-20)'
    )

    args = parser.parse_args()

    # 업로드 항목 결정
    if args.only:
        sync_items = args.only
    else:
        sync_items = SYNC_ITEMS.copy()
        if args.exclude:
            sync_items = [item for item in sync_items if item not in args.exclude]

    # 프로젝트 루트 경로
    project_root = Path(__file__).parent

    # 업로더 실행
    uploader = GDriveUploader(project_root, max_workers=args.workers)
    uploader.sync(sync_items)


if __name__ == '__main__':
    main()
