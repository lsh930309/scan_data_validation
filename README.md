# 📄 Scan Data Validation Tool

OCR 데이터 검수 및 수정을 위한 고속 Gradio 기반 웹 인터페이스

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Gradio](https://img.shields.io/badge/gradio-latest-orange.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## 🎯 주요 기능

- **🖼️ 스마트 이미지 뷰어**: 관심 영역 자동 확대 및 형광펜 하이라이트
- **⚡ 하이브리드 캐싱**: 메모리 + 디스크 캐시로 초고속 이미지 로딩
- **⌨️ 키보드 단축키**: 마우스 없이 빠른 작업 가능
- **✅ 체크박스 지원**: 텍스트와 체크박스 데이터 모두 처리
- **💾 실시간 저장**: 작업 진행 상황 자동 저장
- **👁️ 눈 보호 모드**: Tampermonkey 스크립트로 다크모드 최적화

## 📦 설치

### 1. 필수 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 데이터 준비

프로젝트 루트에 다음 파일들을 배치하세요:

```
scan_data_validation/
├── data.json           # OCR 결과 데이터
├── schema.json         # 양식별 필드 좌표 정의
├── images/            # 스캔 이미지 폴더
│   ├── 001/
│   ├── 002/
│   └── ...
└── cache.json         # 작업 상태 캐시 (자동 생성)
```

## 🚀 사용 방법

### 기본 실행

```bash
python main_v2.py
```

브라우저에서 자동으로 열립니다 (기본: `http://127.0.0.1:7860`)

### 버전 선택

- **`main_v2.py`** (권장): 하이브리드 캐싱 + 최적화 버전
- **`main.py`**: 기본 버전 (캐싱 없음)

## ⌨️ 키보드 단축키

| 키 | 기능 |
|---|---|
| `←` / `→` | 이전/다음 이미지 |
| `↑` / `↓` | 이전/다음 키 필드 |
| `PageUp` / `PageDown` | 이전/다음 양식 |
| `Tab` | 입력창 포커스 이동 |

## 📊 데이터 구조

### `data.json` 형식

```json
{
  "001": {
    "/path/to/image1.jpg": {
      "A": "값1",
      "B": "값2",
      "C": "✔"
    }
  }
}
```

### `schema.json` 형식

```json
{
  "001": {
    "A": {
      "x": 0.5,
      "y": 0.3,
      "ocr_key": "필드명",
      "checkbox": false
    },
    "B": {
      "x": 0.5,
      "y": 0.4,
      "ocr_key": "체크박스",
      "checkbox": true
    }
  }
}
```

## 🎨 눈 보호 모드 (선택 사항)

다크모드에서 흰색 스캔 이미지로 인한 눈부심을 방지하는 Tampermonkey 스크립트를 제공합니다.

### 설치 방법

1. **Tampermonkey 확장 설치**
   - [Chrome](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
   - [Edge](https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd)

2. **스크립트 추가**
   - `gradio_eye_care.user.js` 파일 내용을 복사
   - Tampermonkey → 새 스크립트 작성 → 붙여넣기 → 저장

3. **설정 조정**
   - Gradio 앱 실행 후 우측 상단 "👁️ 설정" 버튼 클릭
   - 밝기/대비/전환속도 조절
   - 변경사항 적용

### 기능

- ✨ 부드러운 이미지 전환 (깜빡임 방지)
- 🌙 자동 밝기 조절 (눈부심 감소)
- 🚫 로딩 인디케이터 제거
- 💾 설정 자동 저장

## 🔧 고급 기능

### 하이브리드 캐싱 시스템 (`main_v2.py`)

- **메모리 캐시**: 최근 15개 이미지 LRU 캐싱
- **디스크 캐시**: `images/_cache/` 폴더에 PNG 저장
- **프리로딩**: 현재 이미지 ±2개 백그라운드 로딩
- **스키마 감지**: `schema.json` 변경 시 자동 캐시 무효화

### 캐시 관리

```bash
# 디스크 캐시 삭제
rm -rf images/_cache/

# 작업 상태 초기화
rm cache.json
```

## 🛠️ 커스터마이징

### 이미지 뷰어 설정 (`main_v2.py:237-343`)

```python
# 확대 비율 조정
crop_w = img_w / 3  # 기본: 1/3 (더 크게 보려면 4, 5 등으로 변경)

# 하이라이트 색상 변경
highlighter_color = (245, 226, 39, 140)  # RGBA

# 디스플레이 크기 조정
display_w, display_h = 1200, 800
```

### 캐싱 설정 (`main_v2.py:18-19`)

```python
MEMORY_CACHE_SIZE = 15  # 메모리 캐시 크기
PRELOAD_RANGE = 2       # 프리로드 범위
```

## 📝 비교 도구

작업 전후 데이터 변경사항을 확인하려면:

```bash
python compare_changes.py
```

출력 예시:
```
=== 양식 001 - 이미지 path/to/image.jpg ===
키 A: "이전값" → "새값"
키 B: "✘" → "✔"
```

## 🤝 기여

개선 사항이나 버그 리포트는 언제든 환영합니다!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📜 라이선스

MIT License - 자유롭게 사용하세요!

## 🙏 감사의 말

- [Gradio](https://gradio.app/) - 빠른 웹 UI 개발
- [Pillow](https://python-pillow.org/) - 이미지 처리
- [Tampermonkey](https://www.tampermonkey.net/) - 브라우저 커스터마이징

---

**Made with ❤️ for efficient OCR data validation**
