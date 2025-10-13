# main_v2.py - 하이브리드 캐싱 시스템 업그레이드

## 개요
main.py의 이미지 뷰어 성능을 개선하기 위해 하이브리드 캐싱 시스템을 구현한 버전입니다.

## 주요 개선 사항

### 1. 하이브리드 캐싱 아키텍처
- **메모리 캐시 (LRU)**: 최근 사용한 15개 이미지를 메모리에 보관
- **디스크 캐시**: 처리된 이미지를 `images/_cache/` 폴더에 PNG로 저장
- **2단계 캐시 조회**: 메모리 → 디스크 → 실시간 생성 순으로 조회

### 2. 성능 최적화
- **프리로딩**: 현재 이미지 ±2개 범위를 백그라운드에서 미리 처리
- **비동기 디스크 저장**: 이미지 저장이 UI를 블로킹하지 않음
- **LRU 정책**: 메모리 캐시가 가득 차면 가장 오래된 항목부터 삭제

### 3. 캐시 무효화
- **schema.json 변경 감지**: MD5 해시로 schema 변경 시 자동으로 캐시 초기화
- **수동 캐시 클리어**: `image_cache.clear_all_cache()` 메서드 제공

## 구현 세부 사항

### HybridImageCache 클래스
```python
class HybridImageCache:
    - get(): 캐시에서 이미지 가져오기 (메모리 → 디스크)
    - put(): 이미지를 캐시에 저장 (메모리 + 디스크)
    - preload_images(): 백그라운드 프리로딩
    - check_schema_changed(): schema.json 변경 감지
    - clear_all_cache(): 모든 캐시 삭제
```

### 캐시 키 구조
```
{form_number}_{key_number}_{index}_{filename}
예: 068_000_0_NSG_044-004 (068).jpg
```

### 디스크 캐시 위치
```
images/_cache/{cache_key}.png
```

## 성능 예상치

### 기존 (main.py)
- 이미지 전환 시: **0.5~1.5초** + 화면 깜빡임

### 개선 후 (main_v2.py)
- **첫 번째 로드**: 0.5~1초 (실시간 생성 + 캐시 저장)
- **두 번째 로드 (메모리 캐시)**: **< 0.05초** (10~30배 빠름)
- **디스크 캐시**: **< 0.1초** (5~15배 빠름)
- **화면 깜빡임**: 거의 없음

## 사용 방법

### 실행
```bash
python main_v2.py
```

### 캐시 관리

#### 캐시 디렉토리 확인
캐시된 이미지는 `images/_cache/` 폴더에 저장됩니다.

#### 수동 캐시 삭제
```bash
# Windows
rmdir /s /q images\_cache

# Python 스크립트에서
from main_v2 import image_cache
image_cache.clear_all_cache()
```

## 설정 조정

main_v2.py 상단에서 다음 설정을 변경할 수 있습니다:

```python
MEMORY_CACHE_SIZE = 15  # 메모리에 보관할 이미지 개수 (기본: 15개)
PRELOAD_RANGE = 2       # 프리로드 범위 (기본: ±2개)
```

### 권장 설정

#### 메모리 64GB (현재 시스템)
```python
MEMORY_CACHE_SIZE = 20  # 더 많은 이미지 캐싱 가능
PRELOAD_RANGE = 3       # 더 넓은 범위 프리로딩
```

#### 메모리 32GB
```python
MEMORY_CACHE_SIZE = 15  # 기본값 유지
PRELOAD_RANGE = 2       # 기본값 유지
```

#### 메모리 16GB 이하
```python
MEMORY_CACHE_SIZE = 10  # 메모리 사용량 줄임
PRELOAD_RANGE = 1       # 프리로드 범위 축소
```

## 주의사항

1. **디스크 공간**: 디스크 캐시는 form×key×image 개수만큼 생성됩니다
   - 예상 용량: 이미지당 1~2MB × 캐시 개수
   - 211개 form × 평균 50개 이미지 × 10개 key = 약 100GB (최대)

2. **schema.json 수정 시**: 자동으로 캐시가 삭제되므로 재생성 시간이 소요됩니다

3. **첫 실행**: 캐시가 비어있으므로 첫 이미지 로딩 시 약간의 지연이 있습니다

4. **호환성**: main.py와 동일한 기능을 제공하므로 언제든 전환 가능합니다

## 문제 해결

### 이미지가 표시되지 않음
1. `images/_cache/` 폴더 삭제 후 재실행
2. schema.json 파일 권한 확인

### 메모리 사용량이 너무 높음
1. `MEMORY_CACHE_SIZE` 값을 줄이기 (예: 10 또는 5)
2. 프로그램 재시작

### 디스크 공간 부족
```bash
# 캐시 폴더 삭제
rmdir /s /q images\_cache
```

## 테스트

```bash
# 캐시 시스템 테스트
python test_cache.py

# 실제 UI 테스트
python main_v2.py
```

## 기술 스택
- **threading**: 백그라운드 프리로딩
- **OrderedDict**: LRU 캐시 구현
- **hashlib**: schema.json 변경 감지 (MD5)
- **PIL/Pillow**: 이미지 처리 및 저장

## 향후 개선 가능 사항
1. 캐시 용량 제한 (디스크 캐시 최대 크기 설정)
2. 캐시 워밍업 (앱 시작 시 자주 사용하는 이미지 프리로드)
3. 통계 추적 (캐시 히트율, 평균 로딩 시간 등)
4. 압축 저장 (PNG 대신 WebP 등 더 작은 포맷 사용)
