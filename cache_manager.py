import json
import threading
import time
import atexit
import os

class CacheManager:
    """
    Gradio 앱의 상태를 메모리에서 관리하고, Debouncing 방식으로 파일에 저장하며,
    안전한 종료를 보장하는 클래스.

    - In-memory state: 상태를 메모리에 유지하여 빠른 읽기/쓰기 지원
    - Debounced saving: 연속된 업데이트 시 마지막 변경 후 일정 시간 뒤에만 저장 (I/O 최소화)
    - Dirty checking: 상태가 변경되었을 때만 파일에 쓰기 수행
    - Graceful shutdown: atexit을 사용하여 프로그램 종료 시 최종 상태 저장 보장
    - Thread safety: Lock을 사용하여 동시 접근으로부터 상태 보호
    """
    def __init__(self, cache_file='cache.json', debounce_delay=2.0):
        """
        Args:
            cache_file (str): 상태를 저장할 JSON 파일 경로
            debounce_delay (float): 마지막 업데이트 후 저장까지 대기 시간 (초)
        """
        self.cache_file = cache_file
        self.debounce_delay = debounce_delay
        self.state = {}
        self._lock = threading.Lock()
        self._is_dirty = False  # 상태 변경 여부 플래그
        self._debounce_timer = None  # Debouncing용 타이머

        self.load()

        # 프로그램 종료 시 최종 저장을 위해 atexit에 등록
        atexit.register(self.stop)

    def load(self):
        """캐시 파일에서 마지막 상태를 로드합니다."""
        with self._lock:
            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, 'r', encoding='utf-8') as f:
                        self.state = json.load(f)
                    print(f"✅ 상태를 '{self.cache_file}'에서 로드했습니다: {self.state}")
                except (json.JSONDecodeError, IOError) as e:
                    print(f"⚠️ '{self.cache_file}' 로드 실패: {e}. 기본 상태로 시작합니다.")
                    self._initialize_default_state()
            else:
                print("ℹ️ 캐시 파일이 없습니다. 기본 상태로 시작합니다.")
                self._initialize_default_state()

    def _initialize_default_state(self):
        """상태 기본값 설정"""
        self.state = {
            'form_number': None,
            'key_number': None,
            'current_index': 0
        }

    def _save_to_disk(self):
        """현재 상태를 디스크에 저장합니다. (내부용)"""
        with self._lock:
            # 변경된 내용이 있을 때만 저장
            if not self._is_dirty:
                return

            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(self.state, f, indent=4, ensure_ascii=False)
                self._is_dirty = False # 저장 후 플래그 초기화
                # print(f"💾 상태 저장 완료: {self.state}") # 디버깅 시 사용
            except IOError as e:
                print(f"❌ 파일 저장 오류: {e}")

    def update_state(self, **kwargs):
        """메모리 내의 상태를 업데이트하고, Debouncing 방식으로 저장을 예약합니다."""
        with self._lock:
            # 하나라도 값이 변경되었는지 확인
            changed = False
            for key, value in kwargs.items():
                if self.state.get(key) != value:
                    self.state[key] = value
                    changed = True

            if changed:
                self._is_dirty = True

        # 변경사항이 있으면 Debouncing 저장 트리거
        if changed:
            self._schedule_debounced_save()

    def _schedule_debounced_save(self):
        """Debouncing: 이전 타이머를 취소하고 새로운 저장 타이머를 시작합니다."""
        # 기존 타이머가 있으면 취소
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()

        # 새로운 타이머 설정
        self._debounce_timer = threading.Timer(self.debounce_delay, self._save_to_disk)
        self._debounce_timer.start()

    def get_state(self):
        """현재 상태를 반환합니다."""
        with self._lock:
            return self.state.copy()

    def force_save(self):
        """즉시 저장을 수행합니다 (브라우저 종료 시 사용)."""
        # 대기 중인 타이머가 있으면 취소
        if self._debounce_timer is not None:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        # 즉시 저장
        self._save_to_disk()

    def stop(self):
        """프로그램 종료 시 최종 상태를 저장합니다."""
        print("\n🛑 CacheManager를 중지합니다. 최종 상태를 저장합니다...")
        self.force_save()
        print("✅ 최종 상태 저장 완료.")
