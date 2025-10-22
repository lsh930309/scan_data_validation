# Google Drive API 설정 가이드

## 1. Google Cloud 프로젝트 설정

### 1-1. Google Cloud Console 접속
1. https://console.cloud.google.com/ 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택

### 1-2. Google Drive API 활성화
1. 좌측 메뉴 → "API 및 서비스" → "라이브러리"
2. "Google Drive API" 검색
3. "사용 설정" 클릭

### 1-3. OAuth 2.0 클라이언트 ID 생성
1. 좌측 메뉴 → "API 및 서비스" → "사용자 인증 정보"
2. "사용자 인증 정보 만들기" → "OAuth 클라이언트 ID"
3. 애플리케이션 유형: "데스크톱 앱"
4. 이름: "scan_data_validation_sync" (또는 원하는 이름)
5. "만들기" 클릭
6. **credentials.json 다운로드** (중요!)

### 1-4. credentials.json 배치
다운로드한 `credentials.json` 파일을 프로젝트 루트에 저장:
```
c:\vscode\project\scan_data_validation\credentials.json
```

**주의**: 이 파일은 `.gitignore`에 추가되어 Git 추적에서 제외됩니다.

## 2. Python 패키지 설치

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client tqdm
```

requirements.txt에도 추가됩니다.

## 3. 첫 실행 시 인증

### 3-1. 업로드 스크립트 실행
```bash
python gdrive_upload.py
```

### 3-2. 브라우저 인증
- 브라우저가 자동으로 열림
- Google 계정 로그인
- "앱이 확인되지 않음" 경고 시: "고급" → "안전하지 않은 페이지로 이동" 클릭
- 권한 허용

### 3-3. 토큰 저장
인증이 완료되면 `token.json` 파일이 자동 생성됩니다.
이 파일도 `.gitignore`에 추가되어 Git 추적에서 제외됩니다.

## 4. 동기화 폴더 구조

Google Drive에 다음 폴더가 생성됩니다:
```
Google Drive/
└── scan_data_validation_backup/
    ├── images/
    ├── csv/
    ├── handout/
    ├── EXTRACT/
    ├── .venv/
    ├── value_masters-v5/
    ├── data.json
    ├── data.json.bak
    └── data_v3.jsonc
```

## 5. 사용 방법

### 회사 PC에서 (업로드)
```bash
# 전체 업로드
python gdrive_upload.py

# 특정 폴더만 업로드
python gdrive_upload.py --only images csv
```

### 집 PC에서 (다운로드)
```bash
# git clone 후
git clone <repository-url>
cd scan_data_validation

# Google Drive에서 데이터 다운로드
python gdrive_download.py

# 가상환경 활성화 (.venv도 다운로드된 경우)
.venv\Scripts\activate

# 또는 새로 가상환경 생성
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 6. 문제 해결

### token.json 만료 시
- 파일 삭제 후 재인증: `del token.json`
- 다시 스크립트 실행하면 브라우저 인증 진행

### credentials.json 분실 시
- Google Cloud Console에서 재다운로드
- 또는 새 OAuth 클라이언트 ID 생성

### 업로드 실패 시
- 인터넷 연결 확인
- Google Drive 용량 확인 (15GB 무료, 약 3.3GB 필요)
- 스크립트 로그 확인

## 7. 보안 주의사항

**절대 Git에 커밋하지 말 것**:
- `credentials.json` - Google OAuth 인증 정보
- `token.json` - 액세스 토큰
- `.gdrive_sync.json` - 로컬 동기화 메타데이터

이들은 모두 `.gitignore`에 등록되어 있습니다.
