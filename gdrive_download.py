#!/usr/bin/env python3
"""
Google Drive 다운로드 스크립트
Google Drive에 백업된 데이터를 로컬로 다운로드합니다.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import io

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from tqdm import tqdm

# OAuth 2.0 권한 범위
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# 다운로드할 항목 목록
SYNC_ITEMS = [
    'images',
    'csv',
    'handout',
    'EXTRACT',
    '.venv',
    'value_masters-v5',
    'data.json',
    'data.json.bak',
    'data_v3.jsonc',
]

# Google Drive 루트 폴더 이름
DRIVE_ROOT_FOLDER = 'scan_data_validation_backup'


class GDriveDownloader:
    """Google Drive 다운로드 관리자"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.credentials_file = project_root / 'credentials.json'
        self.token_file = project_root / 'token.json'
        self.service = None
        self.root_folder_id = None

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

        self.service = build('drive', 'v3', credentials=creds)
        print("✅ Google Drive API 연결 완료")

    def find_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Optional[str]:
        """폴더 찾기"""
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
            return files[0]['id'] if files else None

        except HttpError as error:
            print(f"❌ 폴더 조회 실패: {error}")
            return None

    def list_files_in_folder(self, folder_id: str) -> List[Dict]:
        """폴더 내 파일/폴더 목록 조회"""
        try:
            results = self.service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name, mimeType, size)'
            ).execute()

            return results.get('files', [])

        except HttpError as error:
            print(f"❌ 파일 목록 조회 실패: {error}")
            return []

    def download_file(self, file_id: str, local_path: Path, file_size: Optional[int] = None):
        """파일 다운로드"""
        try:
            request = self.service.files().get_media(fileId=file_id)

            # 부모 디렉토리 생성
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # 다운로드
            with open(local_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False

                # 진행률 표시 (파일 크기가 큰 경우)
                if file_size and file_size > 1024 * 1024:  # 1MB 이상
                    pbar = tqdm(total=100, desc=f"  {local_path.name}", unit="%", leave=False)
                    while not done:
                        status, done = downloader.next_chunk()
                        if status:
                            pbar.update(int(status.progress() * 100) - pbar.n)
                    pbar.close()
                else:
                    while not done:
                        status, done = downloader.next_chunk()

        except HttpError as error:
            print(f"❌ 파일 다운로드 실패 ({local_path}): {error}")
            raise

    def download_folder_recursive(self, folder_id: str, local_path: Path, desc: str = ""):
        """폴더 재귀 다운로드"""
        # 로컬 폴더 생성
        local_path.mkdir(parents=True, exist_ok=True)

        # 폴더 내 항목 조회
        items = self.list_files_in_folder(folder_id)

        if not items:
            print(f"  (빈 폴더)")
            return

        files = [item for item in items if item['mimeType'] != 'application/vnd.google-apps.folder']
        folders = [item for item in items if item['mimeType'] == 'application/vnd.google-apps.folder']

        print(f"  파일 {len(files)}개, 폴더 {len(folders)}개")

        # 파일 다운로드
        for file_item in tqdm(files, desc=desc or f"  다운로드: {local_path.name}", leave=False):
            file_path = local_path / file_item['name']
            file_size = int(file_item.get('size', 0))

            try:
                self.download_file(file_item['id'], file_path, file_size)
            except Exception as e:
                print(f"⚠️  파일 다운로드 실패: {file_path} - {e}")

        # 하위 폴더 재귀 다운로드
        for folder_item in folders:
            subfolder_path = local_path / folder_item['name']
            print(f"  📁 {folder_item['name']}")
            self.download_folder_recursive(folder_item['id'], subfolder_path)

    def download_item(self, item_name: str):
        """개별 항목 다운로드 (파일 또는 폴더)"""
        print(f"📦 {item_name}")

        # Google Drive에서 항목 찾기
        # 먼저 폴더로 시도
        item_id = self.find_folder(item_name, self.root_folder_id)

        if item_id:
            # 폴더인 경우
            local_path = self.project_root / item_name
            self.download_folder_recursive(item_id, local_path, f"다운로드: {item_name}")
        else:
            # 파일인 경우
            query = f"name='{item_name}' and '{self.root_folder_id}' in parents and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size)'
            ).execute()

            files = results.get('files', [])
            if not files:
                print(f"⚠️  {item_name}을(를) Google Drive에서 찾을 수 없습니다.")
                return

            file_item = files[0]
            local_path = self.project_root / item_name
            file_size = int(file_item.get('size', 0))

            print(f"  📄 {item_name} ({file_size / 1024 / 1024:.2f} MB)")
            try:
                self.download_file(file_item['id'], local_path, file_size)
                print(f"  ✅ 완료")
            except Exception as e:
                print(f"  ❌ 실패: {e}")

        print()

    def sync(self, items: Optional[List[str]] = None):
        """동기화 실행"""
        print(f"\n{'='*60}")
        print(f"Google Drive 다운로드 시작")
        print(f"프로젝트: {self.project_root}")
        print(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # 인증
        self.authenticate()

        # 루트 폴더 찾기
        print(f"📁 루트 폴더 확인: {DRIVE_ROOT_FOLDER}")
        self.root_folder_id = self.find_folder(DRIVE_ROOT_FOLDER)

        if not self.root_folder_id:
            print(f"❌ Google Drive에 '{DRIVE_ROOT_FOLDER}' 폴더가 없습니다.")
            print("먼저 회사 PC에서 gdrive_upload.py를 실행하여 데이터를 업로드하세요.")
            sys.exit(1)

        print(f"✅ 폴더 ID: {self.root_folder_id}\n")

        # 다운로드할 항목 결정
        sync_items = items if items else SYNC_ITEMS

        # 항목별 다운로드
        for item_name in sync_items:
            self.download_item(item_name)

        print(f"\n{'='*60}")
        print(f"✅ 모든 다운로드 완료!")
        print(f"프로젝트 폴더: {self.project_root}")
        print(f"{'='*60}\n")

        # 가상환경 안내
        if '.venv' in sync_items and (self.project_root / '.venv').exists():
            print("\n💡 가상환경이 다운로드되었습니다.")
            print("   활성화: .venv\\Scripts\\activate")
        else:
            print("\n💡 가상환경 설정:")
            print("   python -m venv .venv")
            print("   .venv\\Scripts\\activate")
            print("   pip install -r requirements.txt")


def main():
    parser = argparse.ArgumentParser(
        description='Google Drive에서 프로젝트 데이터 다운로드',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  # 전체 다운로드
  python gdrive_download.py

  # 특정 항목만 다운로드
  python gdrive_download.py --only images csv data.json

  # .venv 제외하고 다운로드
  python gdrive_download.py --exclude .venv
        """
    )

    parser.add_argument(
        '--only',
        nargs='+',
        metavar='ITEM',
        help='특정 항목만 다운로드 (예: images csv)'
    )

    parser.add_argument(
        '--exclude',
        nargs='+',
        metavar='ITEM',
        help='특정 항목 제외 (예: .venv)'
    )

    args = parser.parse_args()

    # 다운로드 항목 결정
    if args.only:
        sync_items = args.only
    else:
        sync_items = SYNC_ITEMS.copy()
        if args.exclude:
            sync_items = [item for item in sync_items if item not in args.exclude]

    # 프로젝트 루트 경로
    project_root = Path(__file__).parent

    # 다운로더 실행
    downloader = GDriveDownloader(project_root)
    downloader.sync(sync_items)


if __name__ == '__main__':
    main()
