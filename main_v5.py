import gradio as gr
import json
import os
from PIL import Image, ImageDraw
import copy
import threading
import hashlib
from collections import OrderedDict
from pathlib import Path
import io
import pandas as pd
from cache_manager import CacheManager
from fastapi import FastAPI

# --- Configuration ---
CSV_DIR = 'csv'
SCHEMA_JSON_PATH = 'schema.json'
IMAGE_ROOT_PATH = 'images'
CACHE_JSON_PATH = 'cache.json'
DISK_CACHE_PATH = os.path.join(IMAGE_ROOT_PATH, '_cache')
MEMORY_CACHE_SIZE = 15  # ±2 이미지 + 여유분
PRELOAD_RANGE = 2  # 현재 이미지 기준 ±2개
EXTRACT_DIR = 'EXTRACT'  # CSV 내보내기 폴더

# --- Hybrid Caching System ---
class HybridImageCache:
    """하이브리드 이미지 캐싱 시스템 (메모리 LRU + 디스크 캐시)"""

    def __init__(self):
        self.memory_cache = OrderedDict()
        self.cache_lock = threading.Lock()
        self.preload_executor = None
        self.current_preload_task = None

        # 디스크 캐시 디렉토리 생성
        os.makedirs(DISK_CACHE_PATH, exist_ok=True)

        # schema.json 변경 감지를 위한 해시 저장
        self.schema_hash = self._get_file_hash(SCHEMA_JSON_PATH)

    def _get_file_hash(self, filepath):
        """파일의 MD5 해시를 계산"""
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def _get_cache_key(self, form_number, key_number, image_path, index):
        """캐시 키 생성"""
        return f"{form_number}_{key_number}_{index}_{os.path.basename(image_path)}"

    def _get_disk_cache_path(self, cache_key):
        """디스크 캐시 파일 경로 생성"""
        return os.path.join(DISK_CACHE_PATH, f"{cache_key}.png")

    def get(self, form_number, key_number, image_path, index):
        """캐시에서 이미지 가져오기 (메모리 -> 디스크 순서)"""
        cache_key = self._get_cache_key(form_number, key_number, image_path, index)

        # 1. 메모리 캐시 확인
        with self.cache_lock:
            if cache_key in self.memory_cache:
                # LRU: 최근 사용으로 이동
                self.memory_cache.move_to_end(cache_key)
                return self.memory_cache[cache_key]

        # 2. 디스크 캐시 확인
        disk_path = self._get_disk_cache_path(cache_key)
        if os.path.exists(disk_path):
            try:
                img = Image.open(disk_path)
                img.load()  # 이미지를 메모리에 완전히 로드

                # 메모리 캐시에 추가
                self._add_to_memory_cache(cache_key, img)
                return img
            except Exception as e:
                print(f"디스크 캐시 로드 실패: {e}")
                # 손상된 캐시 파일 삭제
                try:
                    os.remove(disk_path)
                except:
                    pass

        return None

    def put(self, form_number, key_number, image_path, index, image):
        """이미지를 캐시에 저장 (메모리 + 디스크)"""
        cache_key = self._get_cache_key(form_number, key_number, image_path, index)

        # 메모리 캐시에 추가
        self._add_to_memory_cache(cache_key, image)

        # 디스크 캐시에 비동기로 저장
        threading.Thread(
            target=self._save_to_disk,
            args=(cache_key, image),
            daemon=True
        ).start()

    def _add_to_memory_cache(self, cache_key, image):
        """메모리 캐시에 이미지 추가 (LRU)"""
        with self.cache_lock:
            if cache_key in self.memory_cache:
                self.memory_cache.move_to_end(cache_key)
            else:
                self.memory_cache[cache_key] = image
                # 캐시 크기 제한
                if len(self.memory_cache) > MEMORY_CACHE_SIZE:
                    self.memory_cache.popitem(last=False)

    def _save_to_disk(self, cache_key, image):
        """디스크에 이미지 저장"""
        disk_path = self._get_disk_cache_path(cache_key)
        try:
            # RGBA 이미지를 PNG로 저장
            image.save(disk_path, 'PNG', optimize=False)
        except Exception as e:
            print(f"디스크 캐시 저장 실패: {e}")

    def preload_images(self, form_number, key_number, image_files, current_index):
        """현재 인덱스 주변 이미지들을 백그라운드에서 프리로드"""
        # 기존 프리로드 작업 취소 (새로운 작업으로 교체)
        if self.current_preload_task:
            self.current_preload_task = None

        def preload_task():
            task_id = id(threading.current_thread())
            self.current_preload_task = task_id

            # 프리로드할 인덱스 범위 계산
            start_idx = max(0, current_index - PRELOAD_RANGE)
            end_idx = min(len(image_files), current_index + PRELOAD_RANGE + 1)

            for idx in range(start_idx, end_idx):
                # 작업이 취소되었는지 확인
                if self.current_preload_task != task_id:
                    return

                image_path = image_files[idx]
                cache_key = self._get_cache_key(form_number, key_number, image_path, idx)

                # 이미 캐시에 있으면 스킵
                with self.cache_lock:
                    if cache_key in self.memory_cache:
                        continue

                disk_path = self._get_disk_cache_path(cache_key)
                if os.path.exists(disk_path):
                    continue

                # 이미지 생성 및 캐시
                try:
                    processed_img = process_image_for_display(
                        form_number, key_number, image_path, idx
                    )
                    if processed_img and self.current_preload_task == task_id:
                        self.put(form_number, key_number, image_path, idx, processed_img)
                except Exception as e:
                    print(f"프리로드 실패 (idx={idx}): {e}")

        # 백그라운드에서 실행
        threading.Thread(target=preload_task, daemon=True).start()

    def check_schema_changed(self):
        """schema.json이 변경되었는지 확인하고 변경되었으면 캐시 무효화"""
        new_hash = self._get_file_hash(SCHEMA_JSON_PATH)
        if new_hash != self.schema_hash:
            print("schema.json 변경 감지 - 캐시 무효화 중...")
            self.clear_all_cache()
            self.schema_hash = new_hash
            return True
        return False

    def clear_all_cache(self):
        """모든 캐시 삭제"""
        # 메모리 캐시 삭제
        with self.cache_lock:
            self.memory_cache.clear()

        # 디스크 캐시 삭제
        try:
            import shutil
            if os.path.exists(DISK_CACHE_PATH):
                shutil.rmtree(DISK_CACHE_PATH)
                os.makedirs(DISK_CACHE_PATH, exist_ok=True)
        except Exception as e:
            print(f"디스크 캐시 삭제 실패: {e}")

# 전역 캐시 인스턴스
image_cache = HybridImageCache()

# 상태 관리 인스턴스 (Debouncing: 2초 대기 후 저장)
cache_manager = CacheManager(cache_file=CACHE_JSON_PATH, debounce_delay=2.0)

# --- Data Loading ---
def load_json(path):
    """JSON 파일을 로드합니다 (schema.json용)"""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def load_csv_data():
    """csv/ 폴더의 모든 CSV 파일을 로드하여 딕셔너리로 반환합니다"""
    csv_data = {}
    if not os.path.exists(CSV_DIR):
        print(f"경고: {CSV_DIR} 폴더가 없습니다.")
        return csv_data

    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    print(f"📂 {len(csv_files)}개 CSV 파일 로드 중...")

    for csv_file in csv_files:
        form_number = csv_file[:-4]  # 확장자 제거
        csv_path = os.path.join(CSV_DIR, csv_file)
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig', dtype=str)
            csv_data[form_number] = df
            print(f"  ✓ {form_number}: {len(df)}행")
        except Exception as e:
            print(f"  ✗ {form_number}: 로드 실패 - {e}")

    return csv_data

def save_csv_data(form_number, df):
    """특정 form_number의 DataFrame을 CSV 파일로 저장합니다"""
    csv_path = os.path.join(CSV_DIR, f"{form_number}.csv")
    try:
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"💾 {form_number}.csv 저장 완료")
        return True
    except Exception as e:
        print(f"❌ {form_number}.csv 저장 실패: {e}")
        return False

def convert_path(server_path, form_number=None):
    """서버 경로를 로컬 images/ 경로로 변환합니다

    예: /mnt/AI_NAS/.../images/068/A0000.jpg -> images/068/A0000.jpg
    """
    # 방법 1: 'images/' 문자열을 기준으로 분리
    try:
        # 경로 구분자 통일 (\ -> /)
        normalized_path = server_path.replace('\\', '/')

        # 'images/' 뒷부분 추출
        if 'images/' in normalized_path:
            parts = normalized_path.split('images/')
            local_relative_path = parts[-1]  # 마지막 'images/' 이후 부분
            return os.path.join(IMAGE_ROOT_PATH, local_relative_path)
    except Exception as e:
        print(f"경로 변환 실패 (방법1): {e}")

    # 방법 2: form_number와 파일명으로 조합 (fallback)
    if form_number:
        filename = os.path.basename(server_path)
        return os.path.join(IMAGE_ROOT_PATH, form_number, filename)

    # 최종 fallback: 원본 경로 반환
    return server_path

# --- Main Application Logic ---
schema_json = load_json(SCHEMA_JSON_PATH)
csv_data_frames = load_csv_data()  # {form_number: DataFrame}

# CSV 데이터를 converted_data_json 형식으로 변환 (기존 코드와 호환성 유지)
converted_data_json = {}
for form_number, df in csv_data_frames.items():
    if 'image_path' not in df.columns:
        print(f"경고: {form_number}.csv에 image_path 컬럼이 없습니다.")
        continue

    form_data = {}
    for _, row in df.iterrows():
        server_path = row['image_path']
        local_path = convert_path(server_path, form_number)

        # row를 딕셔너리로 변환 (image_path 제외)
        ocr_data = {col: row[col] for col in df.columns if col != 'image_path'}
        form_data[local_path] = ocr_data

    converted_data_json[form_number] = form_data

print(f"✅ 총 {len(converted_data_json)}개 양식 로드 완료")
    
# UI 업데이트를 위한 함수들
def get_form_numbers():
    """CSV 파일과 이미지 폴더가 모두 존재하는 form_number 목록을 반환합니다."""
    all_forms = converted_data_json.keys()
    existing_forms = [
        form for form in all_forms if os.path.isdir(os.path.join(IMAGE_ROOT_PATH, form))
    ]
    return existing_forms

def update_key_dropdown(form_number):
    if not form_number:
        return gr.Dropdown(choices=[], value=None)
    key_numbers = list(schema_json.get(form_number, {}).keys())
    return gr.Dropdown(choices=key_numbers, value=key_numbers[0] if key_numbers else None, interactive=True)

def update_index_dropdown(form_number):
    """form_number에 해당하는 이미지 개수만큼 인덱스 드롭다운을 업데이트"""
    if not form_number:
        return gr.Dropdown(choices=[], value=None)
    image_files = list(converted_data_json.get(form_number, {}).keys())
    if not image_files:
        return gr.Dropdown(choices=[], value=None)
    # 1부터 시작하는 인덱스 목록 생성 (표시용)
    index_choices = [f"{i+1}/{len(image_files)}" for i in range(len(image_files))]
    return gr.Dropdown(choices=index_choices, value=index_choices[0] if index_choices else None, interactive=True)

def generate_interactive_html(pil_image, form_number, button_size=20, debug_mode=True):
    """
    PIL Image와 스키마 데이터를 기반으로 클릭 가능한 버튼이 오버레이된 HTML을 생성합니다.

    :param pil_image: 원본 PIL Image 객체 (형광펜 포함)
    :param form_number: 현재 form_number
    :param button_size: 버튼 크기 (픽셀, 정사각형)
    :param debug_mode: 디버그 모드 활성화 (버튼 테두리 표시)
    :return: Base64 이미지와 절대 위치 버튼이 포함된 HTML 문자열
    """
    import base64
    from io import BytesIO

    # 1. PIL 이미지를 Base64로 인코딩
    buffered = BytesIO()
    pil_image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    img_base64 = f"data:image/png;base64,{img_str}"

    # 2. 버튼 HTML 생성 (모든 key에 대해)
    buttons_html = ""
    schema_data = schema_json.get(form_number, {})

    for key, attrs in schema_data.items():
        x = attrs.get('x')
        y = attrs.get('y')

        # 좌표가 없으면 건너뛰기
        if x is None or y is None:
            continue

        # 좌표 범위 검증 (0.0 ~ 1.0)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            print(f"⚠️ 경고: {key}의 좌표가 범위를 벗어남 (x={x}, y={y})")
            continue

        # 정규화된 좌표를 퍼센트로 변환
        x_percent = x * 100
        y_percent = y * 100

        # 버튼에 key를 data 속성으로 저장
        buttons_html += f"""
        <button
            class="interactive-button"
            style="left: {x_percent}%; top: {y_percent}%;"
            data-key="{key}"
            onclick="handleButtonClick('{key}')"
            title="{key}: {attrs.get('ocr_key', '')}"
        ></button>
        """

    # 3. 최종 HTML 구조화
    # debug_mode에 따라 debug-mode 클래스 추가/제거
    debug_class = "debug-mode" if debug_mode else ""
    html_content = f"""
    <div class="image-container {debug_class}" style="position: relative; display: inline-block; width: 100%;">
        <img src="{img_base64}" alt="Scanned document" style="width: 100%; height: auto; display: block;">
        {buttons_html}
    </div>
    """
    return html_content

def process_image_for_display(form_number, key_number, image_path, index):
    """이미지를 처리하여 디스플레이용 이미지 생성 (원본 전체 표시 + 형광펜)"""
    # 이미지 로드
    if not os.path.exists(image_path):
        return None

    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size

            # 원본 이미지를 그대로 사용 (크롭 없음)
            # RGBA 모드로 변경하여 투명도 처리
            if img.mode != 'RGBA':
                img = img.convert('RGBA')

            # 형광펜 레이어 생성 (Multiply 블렌드 모드 방식)
            # RGB 모드로 작업 후 RGBA로 변환하여 정확한 색상 제어
            base_img_rgb = img.convert('RGB')
            highlighter_layer = Image.new('RGB', img.size, (255, 255, 255))  # 흰색 배경
            draw = ImageDraw.Draw(highlighter_layer)

            # 형광펜 색상 (노란색 - RGB)
            highlighter_color = (255, 230, 100)  # 밝은 노란색

            # 현재 form_number의 모든 key를 순회
            all_keys = schema_json.get(form_number, {})
            ocr_data = converted_data_json.get(form_number, {}).get(image_path, {})

            for current_key, key_info in all_keys.items():
                x = key_info.get('x')
                y = key_info.get('y')
                is_checkbox = key_info.get('checkbox', False)

                # 좌표가 없으면 건너뛰기
                if x is None or y is None:
                    continue

                # OCR 값 가져오기
                ocr_value = ocr_data.get(current_key, "N/A")

                # 조건별 형광펜 그리기 여부 결정
                should_draw = False
                highlighter_size = None

                if is_checkbox:
                    # 체크박스: ✔만 그리기
                    if ocr_value == "✔":
                        should_draw = True
                        highlighter_size = (20, 20)
                else:
                    # 일반 필드: ∅, ␣ 제외
                    if ocr_value not in ["∅", "␣", "N/A"]:
                        should_draw = True
                        # 텍스트 폭 기반 크기 계산
                        text_str = str(ocr_value)
                        display_width = sum(2 if ord(c) > 127 else 1 for c in text_str)
                        highlighter_width = max(20, display_width * 7)
                        highlighter_size = (highlighter_width, 20)

                # 형광펜 그리기
                if should_draw and highlighter_size:
                    # 좌표를 실제 픽셀 좌표로 변환
                    point_x = int(x * img_w)
                    point_y = int(y * img_h)
                    margin_x = 0
                    margin_y = 15

                    draw.rectangle(
                        [point_x + margin_x,
                         point_y + margin_y,
                         point_x + highlighter_size[0] + margin_x,
                         point_y + highlighter_size[1] + margin_y
                         ],
                         fill=highlighter_color
                         )

            # Multiply 블렌드 모드 적용 (형광펜 효과)
            # 원본 픽셀과 형광펜 색상을 곱하여 어두운 부분은 그대로, 밝은 부분만 노랗게
            import numpy as np

            base_array = np.array(base_img_rgb, dtype=np.float32)
            highlighter_array = np.array(highlighter_layer, dtype=np.float32)

            # Multiply 블렌드: (base * highlighter) / 255
            # 검은 글씨(0)는 그대로, 흰 배경(255)은 노란색으로
            blended_array = (base_array * highlighter_array / 255.0).astype(np.uint8)

            result_img = Image.fromarray(blended_array, 'RGB')

            # 최종적으로 RGBA로 변환 (기존 알파 채널 유지)
            result_img = result_img.convert('RGBA')

            return result_img
    except Exception as e:
        print(f"이미지 처리 실패: {e}")
        return None

def update_view(form_number, key_number, current_index, state_data):
    """캐시를 활용한 이미지 뷰 업데이트"""

    # schema 변경 확인
    image_cache.check_schema_changed()

    if not form_number or not key_number:
        return state_data, None, "양식과 키를 선택하세요.", "0 / 0", "", "", False, gr.update(visible=True), gr.update(visible=False, value=None), gr.update(interactive=True), gr.update(interactive=True), gr.update(value=None), gr.update(interactive=True), gr.update(interactive=True)

    # 현재 form_number에 해당하는 이미지 파일 목록 가져오기
    image_files = list(converted_data_json.get(form_number, {}).keys())
    if not image_files:
        return state_data, None, "이미지 파일이 없습니다.", "0 / 0", "", "", False, gr.update(visible=True), gr.update(visible=False, value=None), gr.update(interactive=True), gr.update(interactive=True), gr.update(value=None), gr.update(interactive=True), gr.update(interactive=True)

    total_images = len(image_files)
    # index 보정
    current_index = max(0, min(current_index, total_images - 1))

    image_path = image_files[current_index]

    # schema에서 좌표 및 ocr_key 정보 가져오기
    key_info = schema_json.get(form_number, {}).get(key_number, {})
    x, y = key_info.get('x'), key_info.get('y')
    ocr_key_value = key_info.get('ocr_key', 'N/A')
    is_checkbox = key_info.get('checkbox', False)

    # OCR 데이터 가져오기
    ocr_value = converted_data_json.get(form_number, {}).get(image_path, {}).get(key_number, "N/A")

    # 상태 업데이트
    state_data = {
        "form_number": form_number,
        "key_number": key_number,
        "image_path": image_path,
        "image_files": image_files,
        "current_index": current_index
    }

    # CacheManager를 통해 상태 업데이트 (주기적으로 자동 저장됨)
    cache_manager.update_state(
        form_number=form_number,
        key_number=key_number,
        current_index=current_index
    )

    # 진행 상태 텍스트 생성 (index와 key 진행도 모두 표시)
    key_numbers = list(schema_json.get(form_number, {}).keys())
    current_key_index = key_numbers.index(key_number) if key_number in key_numbers else 0
    total_keys = len(key_numbers)

    if total_images > 0:
        status_text = f"Key: {current_key_index + 1}/{total_keys} | Index: {current_index + 1}/{total_images}"
    else:
        status_text = "Key: 0/0 | Index: 0/0"
    filename = os.path.basename(image_path)

    # is_checkbox 값에 따라 UI 컴포넌트 가시성 조절
    if is_checkbox:
        ocr_textbox_update = gr.update(visible=False, value=ocr_value)
        checkbox_radio_update = gr.update(visible=True, value=ocr_value)
    else:
        ocr_textbox_update = gr.update(visible=True, value=ocr_value)
        checkbox_radio_update = gr.update(visible=False, value=None)

    # === 캐시 활용 이미지 로드 ===
    if os.path.exists(image_path) and x is not None and y is not None:
        # 1. 캐시에서 이미지 가져오기 시도
        zoomed_img = image_cache.get(form_number, key_number, image_path, current_index)

        # 2. 캐시 미스 시 실시간 생성
        if zoomed_img is None:
            zoomed_img = process_image_for_display(form_number, key_number, image_path, current_index)
            if zoomed_img:
                # 생성된 이미지를 캐시에 저장
                image_cache.put(form_number, key_number, image_path, current_index, zoomed_img)

        # 3. 백그라운드 프리로딩 트리거
        image_cache.preload_images(form_number, key_number, image_files, current_index)

        if zoomed_img:
            # HTML 생성 (이미지 + 클릭 가능한 버튼들)
            # debug_mode=True로 설정하면 버튼에 파란색 테두리가 표시됩니다
            html_output = generate_interactive_html(zoomed_img, form_number, debug_mode=False)

            # 버튼 활성화 상태 결정
            prev_btn_interactive = current_index > 0
            next_btn_interactive = current_index < total_images - 1

            # key 버튼 활성화 상태 결정
            key_numbers = list(schema_json.get(form_number, {}).keys())
            current_key_index = key_numbers.index(key_number) if key_number in key_numbers else 0
            prev_key_interactive = current_key_index > 0
            next_key_interactive = current_key_index < len(key_numbers) - 1

            # index_dd 업데이트 (choices와 value 모두 설정)
            index_choices = [f"{i+1}/{total_images}" for i in range(total_images)]
            index_dd_value = f"{current_index + 1}/{total_images}"

            return state_data, html_output, status_text, filename, ocr_key_value, is_checkbox, ocr_textbox_update, checkbox_radio_update, gr.update(interactive=prev_btn_interactive), gr.update(interactive=next_btn_interactive), gr.update(choices=index_choices, value=index_dd_value), gr.update(interactive=prev_key_interactive), gr.update(interactive=next_key_interactive)

    return state_data, None, "0 / 0", f"이미지 경로 오류: {image_path}", ocr_key_value, False, gr.update(value=f"이미지 또는 좌표 없음\nPath: {image_path}"), gr.update(visible=False), gr.update(interactive=True), gr.update(interactive=True), gr.update(value=None), gr.update(interactive=True), gr.update(interactive=True)

def change_image(state_data, direction):
    if not state_data:
        return state_data, None, "상태 정보 없음", "", "", False, gr.update(value="상태 정보 없음"), gr.update(visible=False), gr.update(interactive=True), gr.update(interactive=True), gr.update(value=None), gr.update(interactive=True), gr.update(interactive=True)

    current_index = state_data["current_index"]
    total_images = len(state_data["image_files"])

    # 경계 체크: 범위를 벗어나면 현재 인덱스 유지
    new_index = current_index + direction
    if new_index < 0 or new_index >= total_images:
        new_index = current_index

    return update_view(state_data["form_number"], state_data["key_number"], new_index, state_data)

def change_key(state_data, direction):
    if not state_data or "form_number" not in state_data:
        return gr.Dropdown()

    form_number = state_data["form_number"]
    current_key = state_data.get("key_number")
    
    key_numbers = list(schema_json.get(form_number, {}).keys())
    if not key_numbers:
        return gr.Dropdown(choices=[], value=None)

    try:
        current_key_index = key_numbers.index(current_key)
        new_key_index = (current_key_index + direction + len(key_numbers)) % len(key_numbers)
        new_key = key_numbers[new_key_index]
    except (ValueError, IndexError):
        new_key = key_numbers[0] if key_numbers else None
    
    return gr.Dropdown(value=new_key)

def change_form(state_data, direction):
    form_numbers = get_form_numbers()
    current_form = state_data.get("form_number")

    if not form_numbers:
        return gr.Dropdown(choices=[], value=None)

    try:
        current_form_index = form_numbers.index(current_form)
        new_form_index = (current_form_index + direction + len(form_numbers)) % len(form_numbers)
        new_form = form_numbers[new_form_index]
    except (ValueError, IndexError):
        new_form = form_numbers[0] if form_numbers else None

    return gr.Dropdown(value=new_form)

def determine_empty_value_symbol(df, key_number, form_number):
    """
    DataFrame의 특정 컬럼을 스캔하여 빈 값으로 저장할 기호를 결정합니다.
    기호가 없으면 메모장으로 해당 CSV 파일을 엽니다.

    Args:
        df: 검사할 pandas DataFrame
        key_number: 스캔할 컬럼명
        form_number: CSV 파일 이름 (확장자 제외)

    Returns:
        '∅', '␣' 중 하나를 반환합니다. 발견되지 않으면 None을 반환합니다.
    """
    if key_number not in df.columns:
        print(f"⚠️ 경고: '{key_number}' 컬럼이 DataFrame에 없습니다.")
        return None

    # NaN 값을 제외하고, 모든 값을 문자열로 변환한 뒤 고유한 값들의 집합(set)을 생성
    # set을 사용하면 값 존재 여부 확인 시 성능상 이점이 있습니다. (평균 O(1))
    unique_values = set(df[key_number].dropna().astype(str).unique())

    has_empty_set = '∅' in unique_values
    has_blank = '␣' in unique_values

    # 1. 둘 다 있는 경우 → notepad로 CSV 열기
    if has_empty_set and has_blank:
        print(f"⚠️ '{key_number}' 컬럼에 '∅'와 '␣'가 모두 존재합니다.")
        # notepad 열기 (아래 로직과 동일하게 처리)
        csv_path = os.path.join(CSV_DIR, f"{form_number}.csv")
        try:
            import subprocess
            print(f"📝 메모장으로 {form_number}.csv 파일을 엽니다. 적절한 공란 기호를 확인하세요.")
            subprocess.Popen(['notepad.exe', csv_path])
        except FileNotFoundError:
            print(f"❌ 파일 열기 실패: '{csv_path}' 경로에 파일이 없습니다.")
        except Exception as e:
            print(f"❌ 예상치 못한 오류로 파일 열기에 실패했습니다: {e}")
        return None

    # 2. '∅'만 발견되면 '∅' 반환
    if has_empty_set:
        return '∅'

    # 3. '␣'만 발견되면 '␣' 반환
    if has_blank:
        return '␣'

    # 3. 둘 다 발견되지 않으면 notepad로 CSV 열기
    csv_path = os.path.join(CSV_DIR, f"{form_number}.csv")
    print(f"👉 '{key_number}' 컬럼에서 공란 기호('∅', '␣')를 찾을 수 없습니다.")

    try:
        # os.startfile 대신 subprocess.Popen으로 명시적으로 notepad.exe 실행
        # 이는 파일 연결 상태와 무관하게 항상 메모장에서 열리도록 보장합니다.
        import subprocess
        print(f"📝 메모장으로 {form_number}.csv 파일을 엽니다. 적절한 공란 기호를 확인하세요.")
        subprocess.Popen(['notepad.exe', csv_path])
    except FileNotFoundError:
        print(f"❌ 파일 열기 실패: '{csv_path}' 경로에 파일이 없습니다.")
    except Exception as e:
        print(f"❌ 예상치 못한 오류로 파일 열기에 실패했습니다: {e}")

    return None

def save_data(text_value, radio_value, state_data, request: gr.Request):
    """데이터를 CSV 파일에 직접 저장합니다"""
    if not state_data:
        return "저장할 데이터가 없습니다.", gr.update()

    key_info = schema_json.get(state_data["form_number"], {}).get(state_data["key_number"], {})
    is_checkbox = key_info.get('checkbox', False)

    form_number = state_data["form_number"]
    local_image_path = state_data["image_path"]
    key_number = state_data["key_number"]

    # DataFrame 가져오기
    if form_number not in csv_data_frames:
        return f"오류: {form_number}.csv 파일을 찾을 수 없습니다.", gr.update()

    df = csv_data_frames[form_number]

    if is_checkbox:
        new_value = radio_value
    else:
        # 텍스트 입력값이 비어있거나 공백만 있으면 스마트하게 기호 결정
        if text_value and text_value.strip():
            new_value = text_value
        else:
            # CSV 컬럼을 스캔하여 적절한 공란 기호 결정
            empty_symbol = determine_empty_value_symbol(df, key_number, form_number)
            if empty_symbol is None:
                return "⚠️ CSV 파일을 열었습니다. 적절한 공란 기호('∅' 또는 '␣')를 확인한 후 다시 저장하세요.", gr.update()
            new_value = empty_symbol

    # local_image_path에서 서버 경로 역변환
    # 예: images/068/A0000.jpg -> /mnt/AI_NAS/.../images/068/A0000.jpg
    # 'images/' 이후 부분을 추출
    try:
        normalized_local = local_image_path.replace('\\', '/')
        if 'images/' in normalized_local:
            relative_part = normalized_local.split('images/')[-1]  # '068/A0000.jpg'
        else:
            relative_part = '/'.join(normalized_local.split('/')[-2:])  # fallback

        # DataFrame에서 해당 경로를 포함하는 행 찾기
        # CSV의 image_path는 전체 절대 경로이므로, 끝부분이 일치하는 행을 찾음
        matching_rows = df[df['image_path'].str.endswith(relative_part)]

        if matching_rows.empty:
            return f"오류: CSV에서 경로를 찾을 수 없습니다: {relative_part}", gr.update()

        # DataFrame 업데이트
        row_index = matching_rows.index[0]
        df.loc[row_index, key_number] = new_value

        # converted_data_json도 업데이트 (UI 동기화)
        converted_data_json[form_number][local_image_path][key_number] = new_value

        # CSV 파일에 즉시 저장
        if save_csv_data(form_number, df):
            # UI 업데이트: 저장된 값을 ocr_textbox에 반영
            if not is_checkbox and (new_value == "␣" or new_value == "∅"):
                return f"'{new_value}' (으)로 저장 완료!", gr.update(value=new_value)
            return f"'{new_value}' (으)로 저장 완료!", gr.update()
        else:
            return "오류: CSV 파일 저장 실패", gr.update()

    except Exception as e:
        return f"오류: 경로 변환 실패 - {e}", gr.update()


def open_image_file(state_data):
    if state_data and "image_path" in state_data:
        image_path = state_data["image_path"]
        if os.path.exists(image_path):
            os.startfile(os.path.abspath(image_path))

def export_current_csv(state_data):
    """현재 작업 중인 CSV를 EXTRACT 폴더에 복사하고 폴더를 엽니다"""
    if not state_data or "form_number" not in state_data:
        return "⚠️ 작업 중인 CSV가 없습니다."

    form_number = state_data["form_number"]

    if form_number not in csv_data_frames:
        return f"❌ {form_number}.csv 파일을 찾을 수 없습니다."

    # EXTRACT 폴더 생성
    os.makedirs(EXTRACT_DIR, exist_ok=True)

    # 원본 CSV 경로
    source_csv = os.path.join(CSV_DIR, f"{form_number}.csv")
    # 대상 CSV 경로
    dest_csv = os.path.join(EXTRACT_DIR, f"{form_number}.csv")

    try:
        # CSV 파일 복사
        import shutil
        shutil.copy2(source_csv, dest_csv)

        import subprocess
        subprocess.Popen(['explorer', os.path.abspath(EXTRACT_DIR)])

        print(f"📤 {form_number}.csv를 EXTRACT 폴더로 내보냈습니다.")
        return f"✅ '{form_number}.csv' 내보내기 완료!\nEXTRACT 폴더가 열렸습니다."

    except FileNotFoundError:
        return f"❌ {source_csv} 파일을 찾을 수 없습니다."
    except Exception as e:
        return f"❌ 내보내기 실패: {e}"

# --- Gradio UI ---
# 커스텀 CSS
custom_css = """
.image-container {
    position: relative;
    display: inline-block;
    width: 100%;
}

.interactive-button {
    position: absolute;
    width: 20px;
    height: 20px;
    background-color: rgba(255, 255, 255, 0.0); /* 반투명 파란색 */
    border: none;
    border-radius: 10%; /* 원형 버튼 */
    cursor: pointer;
    padding: 0;

    /* 중요: 중심점 정렬 */
    transform: translate(-0%, -0%);

    transition: background-color 0.2s, transform 0.2s;
    z-index: 10;
}

.interactive-button:hover {
    background-color: rgba(255, 193, 7, 0.7); /* 호버 시 반투명 노란색 */
    transform: translate(-0%, -0%) scale(1.3); /* 살짝 확대 */
}

/* 디버그 모드: debug-mode 클래스 제거 시 테두리 숨김 */
.debug-mode .interactive-button {
    border: 0.1px solid blue;
}

/* 히든 트리거 컴포넌트 숨기기 (DOM에는 유지) */
#hidden-trigger-group {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    overflow: hidden !important;
}
"""

js_keyboard_shortcuts = """
() => {
    // 버튼 클릭 핸들러 (전역 함수)
    window.handleButtonClick = function(key) {
        console.log('🔘 Button clicked:', key);

        // 1. Gradio의 히든 Textbox에 값 설정
        // Gradio Textbox 구조: div#key-input > label > textarea
        const keyInput = document.querySelector("#key-input textarea");
        if (keyInput) {
            console.log('✅ Found textarea, setting value:', key);
            keyInput.value = key;

            // Gradio가 감지할 수 있도록 input 이벤트 발생
            keyInput.dispatchEvent(new Event('input', { bubbles: true }));
            keyInput.dispatchEvent(new Event('change', { bubbles: true }));
        } else {
            console.error('❌ Textarea not found! Selector: #key-input textarea');
            // 디버깅: DOM 구조 확인
            const keyInputDiv = document.querySelector("#key-input");
            console.log('key-input div:', keyInputDiv);
            if (keyInputDiv) {
                console.log('innerHTML:', keyInputDiv.innerHTML);
            }
        }

        // 2. Gradio의 히든 Button 클릭하여 Python 함수 트리거
        // Gradio Button의 elem_id는 button 태그 자체에 적용됨
        const triggerButton = document.querySelector("#trigger-button");
        if (triggerButton) {
            console.log('✅ Found trigger button, clicking...');
            triggerButton.click();
        } else {
            console.error('❌ Trigger button not found! Selector: #trigger-button');
        }

        return key;
    };

    // 키보드 단축키
    document.addEventListener('keydown', (e) => {
        // 텍스트 입력창에 포커스가 있을 때
        if (e.target.nodeName === "INPUT" || e.target.nodeName === "TEXTAREA") {
            // Enter 키를 누르면 저장 버튼 클릭
            if (e.key === 'Enter') {
                e.preventDefault(); // 기본 동작 방지
                e.target.blur(); // 포커스 해제
                document.getElementById('save_button').click();
            }
            return;
        }

        // 텍스트 입력창 외부에서의 단축키
        if (e.key === 'ArrowLeft') {
            document.getElementById('prev_button').click();
        } else if (e.key === 'ArrowRight') {
            document.getElementById('next_button').click();
        } else if (e.key === 'ArrowUp') {
            document.getElementById('prev_key_button').click();
        } else if (e.key === 'ArrowDown') {
            document.getElementById('next_key_button').click();
        } else if (e.key === 'PageUp') {
            document.getElementById('prev_form_button').click();
        } else if (e.key === 'PageDown') {
            document.getElementById('next_form_button').click();
        }
    });

    // 브라우저 종료/새로고침 시 캐시 저장
    window.addEventListener('beforeunload', () => {
        navigator.sendBeacon('/api/save-cache', new Blob());
    });
}
"""

with gr.Blocks(title="OCR 데이터 검수 도구 v5", css=custom_css, js=js_keyboard_shortcuts) as demo:
    # 상태 저장을 위한 변수
    state = gr.State({})

    # gr.Markdown("# OCR 데이터 검수 및 수정 도구")

    # 이전 세션 정보 표시
    cached_state = cache_manager.get_state()
    if cached_state.get("form_number") and cached_state.get("key_number"):
        cache_info = f"**📌 이전 작업**: Form `{cached_state['form_number']}`, Key `{cached_state['key_number']}`, Index `{cached_state.get('current_index', 0)+1}`"
    else:
        cache_info = "**ℹ️ 새로운 세션**"

    # 히든 컴포넌트들 (DOM에는 유지, CSS로 숨김)
    with gr.Group(elem_id="hidden-trigger-group"):
        key_input = gr.Textbox(elem_id="key-input", label="Hidden Key Input", container=False)
        trigger_button = gr.Button(elem_id="trigger-button", value="Trigger", size="sm")

    with gr.Row():
        # 좌측: 컴팩트 컨트롤 패널
        with gr.Column(scale=1):
            gr.Markdown(cache_info)
            status_label = gr.Label(value="0 / 0", label="진행 상태")

            with gr.Group():
                gr.Markdown("### 데이터 선택")
                with gr.Row():
                    form_number_dd = gr.Dropdown(choices=get_form_numbers(), label="Form Number", interactive=True)
                    key_number_dd = gr.Dropdown(label="Key Number", interactive=True)
                    index_dd = gr.Dropdown(label="Index", interactive=True)
                # Index 고정 기능을 항상 활성화 (체크박스는 숨김)
                fix_index_checkbox = gr.Checkbox(label="Index 고정", value=True, visible=False)

            with gr.Group():
                gr.Markdown("### 파일 정보")
                with gr.Row():
                    filename_textbox = gr.Textbox(label="Filename", interactive=False)
                    is_checkbox_textbox = gr.Textbox(label="Type", interactive=False)
                ocr_key_textbox = gr.Textbox(label="OCR Key", interactive=False)
                open_file_btn = gr.Button("📂 파일 열기", variant="secondary")

            with gr.Group():
                gr.Markdown("### 데이터 입력")
                ocr_textbox = gr.Textbox(label="OCR 값", interactive=True, visible=True)
                checkbox_radio = gr.Radio(["✘", "✔"], label="OCR 값", visible=False, interactive=True)
                save_status = gr.Textbox(label="저장 상태", interactive=False, show_label=False)
                save_btn = gr.Button("💾 저장 (Enter)", elem_id="save_button", variant="secondary")

            with gr.Group():
                gr.Markdown("### 네비게이션")
                with gr.Row():
                    prev_btn = gr.Button("← 이전", elem_id="prev_button", scale=1)
                    next_btn = gr.Button("다음 →", elem_id="next_button", scale=1)
                    prev_form_button = gr.Button("⇞ 이전 Form", elem_id="prev_form_button", scale=1)
                with gr.Row():
                    prev_key_button = gr.Button("↑ 이전 Key", elem_id="prev_key_button", scale=1)
                    next_key_button = gr.Button("↓ 다음 Key", elem_id="next_key_button", scale=1)
                    next_form_button = gr.Button("⇟ 다음 Form", elem_id="next_form_button", scale=1)

            with gr.Group():
                gr.Markdown("### 기타")
                export_btn = gr.Button("📤 CSV 내보내기", variant="primary")
                export_status = gr.Textbox(label="내보내기 상태", interactive=False, show_label=False)

        # 우측: 세로로 긴 이미지 뷰어 (A4 비율 1:1.414)
        with gr.Column(scale=1.2):
            image_display = gr.HTML(label="이미지 뷰어 (클릭 가능)")

    # --- Event Listeners ---
    # state를 맨 앞에 배치하여 먼저 업데이트되도록 함 (빠른 키 입력 시 동기화 문제 방지)
    outputs_list = [state, image_display, status_label, filename_textbox, ocr_key_textbox, is_checkbox_textbox, ocr_textbox, checkbox_radio, prev_btn, next_btn, index_dd, prev_key_button, next_key_button]

    # form 변경 시: key_number 초기화 및 뷰 업데이트
    def on_form_change(form, state):
        if not form:
            empty_dropdown = gr.Dropdown(choices=[], value=None)
            return [empty_dropdown] + [state] + [gr.update() for _ in range(len(outputs_list) - 1)]

        # 첫 번째 key 가져오기
        key_numbers = list(schema_json.get(form, {}).keys())
        first_key = key_numbers[0] if key_numbers else None

        # key_number 드롭다운 업데이트
        key_dropdown_update = gr.Dropdown(choices=key_numbers, value=first_key, interactive=True)

        # index=0으로 초기화하여 뷰 업데이트
        if first_key:
            return [key_dropdown_update] + list(update_view(form, first_key, 0, state))
        else:
            return [key_dropdown_update] + [state] + [gr.update() for _ in range(len(outputs_list) - 1)]

    form_number_dd.change(
        fn=on_form_change,
        inputs=[form_number_dd, state],
        outputs=[key_number_dd] + outputs_list
    )

    # key 변경 시: Index 고정이 활성화되어 있으므로 항상 현재 index 유지
    def on_key_change(form, key, fix_index, state):
        if fix_index and state and "current_index" in state:
            # Index 고정: 현재 index 유지
            return update_view(form, key, state["current_index"], state)
        else:
            # Index 고정 해제: index를 0으로 리셋
            return update_view(form, key, 0, state)

    key_number_dd.change(
        fn=on_key_change,
        inputs=[form_number_dd, key_number_dd, fix_index_checkbox, state],
        outputs=outputs_list
    )
    
    # 이전/다음 버튼 클릭 이벤트
    prev_btn.click(
        fn=lambda s: change_image(s, -1),
        inputs=[state],
        outputs=outputs_list
    )
    next_btn.click(
        fn=lambda s: change_image(s, 1),
        inputs=[state],
        outputs=outputs_list
    )

    # 저장 버튼 클릭 이벤트
    save_btn.click(
        fn=save_data,
        inputs=[ocr_textbox, checkbox_radio, state, ],
        outputs=[save_status, ocr_textbox]
    )

    open_file_btn.click(
        fn=open_image_file,
        inputs=[state],
        outputs=None
    )

    # 숨겨진 버튼 이벤트 리스너
    prev_key_button.click(
        fn=lambda s: change_key(s, -1),
        inputs=[state],
        outputs=[key_number_dd]
    )
    next_key_button.click(
        fn=lambda s: change_key(s, 1),
        inputs=[state],
        outputs=[key_number_dd]
    )
    prev_form_button.click(
        fn=lambda s: change_form(s, -1),
        inputs=[state],
        outputs=[form_number_dd]
    )
    next_form_button.click(
        fn=lambda s: change_form(s, 1),
        inputs=[state],
        outputs=[form_number_dd]
    )

    # 내보내기 버튼 클릭 이벤트
    export_btn.click(
        fn=export_current_csv,
        inputs=[state],
        outputs=[export_status]
    )

    # index_dd 변경 시 해당 인덱스로 이동
    def on_index_change(index_str, state):
        if not index_str or not state:
            return outputs_list
        # "1/10" 형식에서 숫자 추출
        try:
            current = int(index_str.split('/')[0]) - 1  # 0-based index로 변환
            return update_view(state["form_number"], state["key_number"], current, state)
        except:
            return update_view(state["form_number"], state["key_number"], state["current_index"], state)

    index_dd.change(
        fn=on_index_change,
        inputs=[index_dd, state],
        outputs=outputs_list
    )

    # 히든 트리거 버튼 클릭 시 key_number_dd 값 변경
    def handle_button_click_trigger(clicked_key):
        """JavaScript에서 클릭한 버튼의 key 값으로 dropdown 업데이트"""
        print(f"🔘 버튼 클릭 감지: {clicked_key}")
        return gr.Dropdown(value=clicked_key)

    trigger_button.click(
        fn=handle_button_click_trigger,
        inputs=[key_input],
        outputs=[key_number_dd]
    )

    # --- App Load Event (cache에서 전체 상태 로드) ---
    def on_load_full():
        """cache에서 form_number만 불러오기 (나머지는 순차적으로 로드)"""
        cache = cache_manager.get_state()
        form_number = cache.get("form_number")

        all_forms = get_form_numbers()
        if not form_number or form_number not in all_forms:
            form_number = all_forms[0] if all_forms else None

        return form_number

    def on_load_step2(form_number):
        """form_number 설정 후 key_number를 cache에서 불러오기"""
        if not form_number:
            return gr.Dropdown(choices=[], value=None, interactive=False)

        cache = cache_manager.get_state()
        cached_key = cache.get("key_number")

        all_keys = list(schema_json.get(form_number, {}).keys())

        # cached key가 유효하면 사용, 아니면 첫 번째 key
        if cached_key and cached_key in all_keys:
            key_number = cached_key
        else:
            key_number = all_keys[0] if all_keys else None

        return gr.Dropdown(choices=all_keys, value=key_number, interactive=True)

    def on_load_step3(form_number, key_number, state):
        """key_number 설정 후 view를 cache의 index로 업데이트"""
        if not form_number or not key_number:
            return [state] + [gr.update() for _ in range(len(outputs_list) - 1)]

        cache = cache_manager.get_state()
        current_index = cache.get("current_index", 0)

        # cache에서 불러온 index로 view 업데이트
        return update_view(form_number, key_number, current_index, state)

    # 순차적 로드: form → key → view (모두 cache에서)
    load_event = demo.load(
        fn=on_load_full,
        inputs=None,
        outputs=[form_number_dd]
    )

    load_event.then(
        fn=on_load_step2,
        inputs=[form_number_dd],
        outputs=[key_number_dd]
    ).then(
        fn=on_load_step3,
        inputs=[form_number_dd, key_number_dd, state],
        outputs=outputs_list
    )


# --- FastAPI 앱 생성 및 Gradio 마운트 ---
app = FastAPI()

# 브라우저 종료 시 캐시 저장 엔드포인트
@app.post("/api/save-cache")
async def save_cache_api():
    print("📡 브라우저에서 저장 요청 수신")
    cache_manager.force_save()
    return {"status": "saved"}

# Gradio 앱을 FastAPI에 마운트
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    print("🚀 FastAPI + Gradio 서버 시작")
    print("📍 접속 주소: http://127.0.0.1:7860")
    uvicorn.run(app, host="127.0.0.1", port=7860)
