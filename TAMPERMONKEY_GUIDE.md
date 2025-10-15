# Gradio OCR Tool - State Persistence 설치 가이드

Gradio 앱의 작업 상태(form_number, key_number, image_index)를 브라우저에 자동 저장하고 복원하는 Tampermonkey 스크립트입니다.

## 기능

- ✅ **자동 저장**: Form/Key/Image 변경 시 자동으로 localStorage에 저장
- ✅ **자동 복원**: 브라우저 새로고침 시 마지막 작업 위치로 자동 복원
- ✅ **디바운싱**: 빠른 연속 변경 시 500ms 후 한 번만 저장 (성능 최적화)
- ✅ **완벽한 상태 복원**: Form → Key → Image Index 순서대로 복원

## 설치 방법

### 1. Tampermonkey 확장 프로그램 설치

**Chrome/Edge:**
1. [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)에서 설치
2. "Chrome에 추가" 클릭

**Firefox:**
1. [Firefox Add-ons](https://addons.mozilla.org/ko/firefox/addon/tampermonkey/)에서 설치
2. "Firefox에 추가" 클릭

### 2. 스크립트 설치

1. Tampermonkey 아이콘 클릭 → "새 스크립트 작성" 선택
2. 편집기에 `gradio_state_persistence.user.js` 파일 내용 전체 복사/붙여넣기
3. `Ctrl+S` 또는 File → Save 클릭

또는:

1. `gradio_state_persistence.user.js` 파일을 브라우저로 드래그&드롭
2. Tampermonkey가 자동으로 설치 확인 창 표시 → "설치" 클릭

### 3. 스크립트 활성화 확인

1. Gradio 앱 접속: `http://localhost:7860` 또는 `http://127.0.0.1:7860`
2. `F12` 키로 개발자 도구 열기
3. Console 탭에서 다음 메시지 확인:
   ```
   [Gradio State] Script loaded
   [Gradio State] Initializing...
   [Gradio State] Observer initialized
   [Gradio State] Button listeners attached
   [Gradio State] Initialization complete
   ```

## 사용 방법

### 자동 저장
- Form/Key/Image를 변경하면 자동으로 저장됩니다
- Console에 `[Gradio State] Saved: {...}` 메시지가 출력됩니다

### 자동 복원
1. 작업 중 브라우저 새로고침 (`F5`)
2. 자동으로 마지막 작업 위치로 복원됩니다:
   - Form Number 선택
   - Key Number 선택
   - Image Index 복원 (다음 버튼 자동 클릭)

### 저장된 상태 확인
브라우저 Console에서:
```javascript
JSON.parse(localStorage.getItem('gradio_ocr_state'))
```

### 저장된 상태 삭제
브라우저 Console에서:
```javascript
localStorage.removeItem('gradio_ocr_state')
```

## 동작 원리

1. **저장 트리거**:
   - Form/Key dropdown 변경 감지 (MutationObserver)
   - 이전/다음 버튼 클릭 감지
   - 페이지 언로드 시 (beforeunload)

2. **저장 데이터**:
   ```json
   {
     "form_number": "259",
     "key_number": "003",
     "current_index": 42,
     "timestamp": 1234567890
   }
   ```

3. **복원 프로세스**:
   ```
   페이지 로드
   → Form dropdown 설정 (이벤트 발동)
   → 1초 대기
   → Key dropdown 설정 (이벤트 발동)
   → 1초 대기
   → 다음 버튼 자동 클릭 (current_index만큼)
   ```

## 문제 해결

### 스크립트가 작동하지 않음
1. Tampermonkey 아이콘 → 대시보드 확인
2. 스크립트가 활성화되어 있는지 확인 (체크박스)
3. URL 매칭 확인: `http://127.0.0.1:7860/*` 또는 `http://localhost:7860/*`

### 상태가 복원되지 않음
1. `F12` → Console 탭에서 에러 메시지 확인
2. `localStorage.getItem('gradio_ocr_state')` 값 확인
3. Gradio 앱이 완전히 로드된 후 복원되는지 대기

### Image Index가 정확히 복원되지 않음
- `restoreImageIndex` 함수의 `clickInterval` 값 조정 (현재 300ms)
- 네트워크가 느린 경우 500ms로 증가:
  ```javascript
  }, 500); // 300ms → 500ms
  ```

## 커스터마이징

### 저장 딜레이 조정
```javascript
const SAVE_DELAY = 500; // 500ms → 1000ms로 변경
```

### 복원 딜레이 조정
```javascript
setTimeout(() => {
    // Key 복원
}, 1000); // 1000ms → 2000ms로 변경
```

### 다른 포트에서 실행 시
스크립트 상단 수정:
```javascript
// @match        http://127.0.0.1:7860/*
// @match        http://127.0.0.1:8080/*  // 추가
```

## 주의사항

- ⚠️ **localStorage는 브라우저별로 독립적**: Chrome과 Firefox는 별도로 저장됩니다
- ⚠️ **시크릿 모드에서는 작동하지 않음**: localStorage가 비활성화됩니다
- ⚠️ **브라우저 캐시 삭제 시 초기화**: localStorage도 함께 삭제됩니다

## 버전 정보

- **Version**: 1.0
- **Author**: Claude Code
- **License**: MIT
- **Created**: 2025-01-15

## 기여

버그 리포트나 개선 제안은 이슈로 등록해주세요.
