import json
import os
import re
import glob

# --- Configuration ---
DATA_JSON_PATH = 'data.json'
BACKUP_JSON_PATH = 'data.json.bak' # 비교할 원본 파일
HANDOUT_DIR = 'handout'  # 출력 디렉토리

# --- Auto Versioning ---
def get_next_version_filename():
    """
    handout 폴더의 기존 파일들을 확인하여 다음 버전 번호를 자동으로 결정합니다.
    예: data_v1.jsonc, data_v2.jsonc가 있으면 data_v3.jsonc를 반환
    """
    # handout 디렉토리가 없으면 생성
    if not os.path.exists(HANDOUT_DIR):
        os.makedirs(HANDOUT_DIR)
        print(f"'{HANDOUT_DIR}' 폴더를 생성했습니다.")
        return os.path.join(HANDOUT_DIR, 'data_v1.jsonc')

    # data_v*.jsonc 패턴의 파일 찾기
    pattern = os.path.join(HANDOUT_DIR, 'data_v*.jsonc')
    existing_files = glob.glob(pattern)

    if not existing_files:
        # 버전 파일이 없으면 v1부터 시작
        return os.path.join(HANDOUT_DIR, 'data_v1.jsonc')

    # 기존 파일에서 버전 번호 추출
    version_numbers = []
    for filepath in existing_files:
        filename = os.path.basename(filepath)
        # data_v숫자.jsonc 패턴에서 숫자 추출
        match = re.search(r'data_v(\d+)\.jsonc', filename)
        if match:
            version_numbers.append(int(match.group(1)))

    if version_numbers:
        # 가장 큰 버전 번호 + 1
        next_version = max(version_numbers) + 1
    else:
        next_version = 1

    next_filename = os.path.join(HANDOUT_DIR, f'data_v{next_version}.jsonc')
    print(f"다음 버전 파일명: {next_filename}")
    return next_filename

# --- Data Loading ---
def load_json(path):
    """지정된 경로의 JSON 파일을 로드합니다."""
    if not os.path.exists(path):
        print(f"오류: 파일이 존재하지 않습니다 - {path}")
        return None
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"오류: JSON 디코딩 실패 - {path}\n{e}")
            return None

def find_changes(old_data, new_data):
    """
    두 데이터 딕셔너리를 비교하여 변경된 값의 원래 값을 추적합니다.
    반환값: {(form, image, key): old_value} 형태의 딕셔너리
    """
    changes = {}
    old_forms = set(old_data.keys())
    new_forms = set(new_data.keys())
    common_forms = old_forms & new_forms

    for form in common_forms:
        if form not in new_data: continue
        old_images = set(old_data.get(form, {}).keys())
        new_images = set(new_data.get(form, {}).keys())
        common_images = old_images & new_images

        for image_path in common_images:
            if image_path not in new_data[form]: continue
            old_ocr_data = old_data[form][image_path]
            new_ocr_data = new_data[form][image_path]
            old_keys = set(old_ocr_data.keys())
            new_keys = set(new_ocr_data.keys())
            common_keys = old_keys & new_keys

            for key in common_keys:
                if key not in new_ocr_data: continue
                old_value = old_ocr_data[key]
                new_value = new_ocr_data[key]
                if old_value != new_value:
                    changes[(form, image_path, key)] = old_value
    return changes

def generate_jsonc(data, changes):
    """
    데이터와 변경점을 기반으로 주석이 포함된 JSONC 형식의 문자열을 생성합니다.
    """
    lines = []
    lines.append("{")

    for i, (form, images) in enumerate(data.items()):
        lines.append(f'  "{form}": {{')
        for j, (image_path, ocr_data) in enumerate(images.items()):
            # JSON 문자열 내의 백슬래시를 이스케이프 처리합니다.
            escaped_image_path = image_path.replace('\\', '\\\\')
            lines.append(f'    "{escaped_image_path}": {{')
            
            num_keys = len(ocr_data)
            for k, (key, value) in enumerate(ocr_data.items()):
                # JSON 문자열로 만들기 위해 값을 다시 인코딩합니다.
                value_str = json.dumps(value, ensure_ascii=False)
                line = f'      "{key}": {value_str}'
                
                # JSONC 형식을 위해 쉼표를 먼저 추가합니다.
                if k < num_keys - 1:
                    line += ','
                    
                # 변경점 주석 추가
                change_key = (form, image_path, key)
                if change_key in changes:
                    old_value = changes[change_key]
                    old_value_str = json.dumps(old_value, ensure_ascii=False)
                    line += f' // original: {old_value_str}'
                lines.append(line)

            line_suffix = ',' if j < len(images) - 1 else ''
            lines.append(f'    }}{line_suffix}')

        line_suffix = ',' if i < len(data) - 1 else ''
        lines.append(f'  }}{line_suffix}')

    lines.append("}")
    return '\n'.join(lines)

def save_to_file(content, path):
    """문자열 콘텐츠를 지정된 경로에 저장합니다."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"성공: 변경점이 '{path}' 파일에 저장되었습니다.")
    except IOError as e:
        print(f"오류: 파일을 저장하는 데 실패했습니다 - {path}\n{e}")

if __name__ == "__main__":
    old_data = load_json(BACKUP_JSON_PATH)
    new_data = load_json(DATA_JSON_PATH)

    if old_data is not None and new_data is not None:
        changes = find_changes(old_data, new_data)
        if not changes:
            print("--- 변경점이 없습니다. ---")
        else:
            print(f"--- {len(changes)}개의 변경점을 발견했습니다. ---")

            # 자동으로 다음 버전 파일명 결정
            output_path = get_next_version_filename()

            jsonc_content = generate_jsonc(new_data, changes)
            save_to_file(jsonc_content, output_path)