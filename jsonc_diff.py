#!/usr/bin/env python3
"""
JSONC File Difference Extractor
두 개의 JSONC 파일을 비교하여 차이점만 추출하는 GUI 도구
"""

import json
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Any, Dict, List, Tuple


def remove_jsonc_comments(text: str) -> str:
    """JSONC에서 주석을 제거하여 순수 JSON으로 변환"""
    # 줄 단위 주석 제거 (//)
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    # 블록 주석 제거 (/* */)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    return text


def load_jsonc(file_path: str) -> Any:
    """JSONC 파일을 로드"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 주석 제거
    json_content = remove_jsonc_comments(content)

    # JSON 파싱
    return json.loads(json_content)


def get_differences(old_data: Any, new_data: Any, path: str = "") -> Dict[str, Any]:
    """
    두 데이터 구조를 비교하여 차이점만 추출
    old_data: 이전 버전
    new_data: 최신 버전
    반환: 최신 버전에서 변경되거나 추가된 항목만 포함
    """
    if type(old_data) != type(new_data):
        # 타입이 다르면 전체를 새 값으로 간주
        return new_data

    if isinstance(new_data, dict):
        diff = {}

        # 새 데이터의 모든 키 검사
        for key in new_data:
            new_path = f"{path}.{key}" if path else key

            if key not in old_data:
                # 새로 추가된 키
                diff[key] = new_data[key]
            elif old_data[key] != new_data[key]:
                # 값이 변경된 키
                nested_diff = get_differences(old_data[key], new_data[key], new_path)
                if nested_diff is not None:
                    if isinstance(nested_diff, dict) and len(nested_diff) == 0:
                        # 빈 dict는 제외
                        continue
                    diff[key] = nested_diff

        return diff if diff else {}

    elif isinstance(new_data, list):
        # 리스트가 완전히 다르면 새 리스트 반환
        if old_data != new_data:
            return new_data
        return []

    else:
        # 기본 타입 (str, int, bool, etc.)
        if old_data != new_data:
            return new_data
        return None


def format_as_jsonc(data: Any, indent: int = 2) -> str:
    """데이터를 JSONC 형식으로 포맷팅"""
    # 보기 좋게 들여쓰기된 JSON으로 변환
    json_str = json.dumps(data, ensure_ascii=False, indent=indent)

    # JSONC 헤더 추가
    header = "// 차이점 추출 결과 (변경되거나 추가된 항목만 포함)\n"
    return header + json_str


class JsoncDiffApp:
    def __init__(self, root):
        self.root = root
        self.root.title("JSONC 파일 차이점 추출기")
        self.root.geometry("600x300")

        self.old_file = None
        self.new_file = None

        self.create_widgets()

    def create_widgets(self):
        # 제목
        title = tk.Label(
            self.root,
            text="JSONC 파일 차이점 추출기",
            font=("Arial", 16, "bold"),
            pady=20
        )
        title.pack()

        # 설명
        description = tk.Label(
            self.root,
            text="이전 버전과 최신 버전의 JSONC 파일을 선택하세요",
            font=("Arial", 10)
        )
        description.pack()

        # 파일 선택 프레임
        file_frame = tk.Frame(self.root, pady=20)
        file_frame.pack()

        # 이전 버전 파일 선택
        old_frame = tk.Frame(file_frame)
        old_frame.pack(pady=5)

        tk.Label(old_frame, text="1. 이전 버전:", width=12, anchor="w").pack(side=tk.LEFT)
        self.old_file_label = tk.Label(
            old_frame,
            text="파일을 선택하세요",
            width=40,
            anchor="w",
            relief=tk.SUNKEN,
            padx=5
        )
        self.old_file_label.pack(side=tk.LEFT, padx=5)

        old_btn = tk.Button(
            old_frame,
            text="찾아보기",
            command=self.select_old_file,
            width=10
        )
        old_btn.pack(side=tk.LEFT)

        # 최신 버전 파일 선택
        new_frame = tk.Frame(file_frame)
        new_frame.pack(pady=5)

        tk.Label(new_frame, text="2. 최신 버전:", width=12, anchor="w").pack(side=tk.LEFT)
        self.new_file_label = tk.Label(
            new_frame,
            text="파일을 선택하세요",
            width=40,
            anchor="w",
            relief=tk.SUNKEN,
            padx=5
        )
        self.new_file_label.pack(side=tk.LEFT, padx=5)

        new_btn = tk.Button(
            new_frame,
            text="찾아보기",
            command=self.select_new_file,
            width=10
        )
        new_btn.pack(side=tk.LEFT)

        # 실행 버튼
        btn_frame = tk.Frame(self.root, pady=20)
        btn_frame.pack()

        self.compare_btn = tk.Button(
            btn_frame,
            text="차이점 추출하기",
            command=self.compare_files,
            font=("Arial", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            padx=20,
            pady=10,
            state=tk.DISABLED
        )
        self.compare_btn.pack()

    def select_old_file(self):
        file_path = filedialog.askopenfilename(
            title="이전 버전 JSONC 파일 선택",
            filetypes=[("JSONC files", "*.jsonc"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.old_file = file_path
            self.old_file_label.config(text=Path(file_path).name)
            self.check_enable_compare()

    def select_new_file(self):
        file_path = filedialog.askopenfilename(
            title="최신 버전 JSONC 파일 선택",
            filetypes=[("JSONC files", "*.jsonc"), ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            self.new_file = file_path
            self.new_file_label.config(text=Path(file_path).name)
            self.check_enable_compare()

    def check_enable_compare(self):
        if self.old_file and self.new_file:
            self.compare_btn.config(state=tk.NORMAL)

    def compare_files(self):
        try:
            # 파일 로드
            old_data = load_jsonc(self.old_file)
            new_data = load_jsonc(self.new_file)

            # 차이점 추출
            differences = get_differences(old_data, new_data)

            # 결과가 없는 경우
            if not differences or (isinstance(differences, dict) and len(differences) == 0):
                messagebox.showinfo("결과", "두 파일 간 차이점이 없습니다.")
                return

            # 저장 경로 선택
            output_path = filedialog.asksaveasfilename(
                title="차이점 파일 저장",
                defaultextension=".jsonc",
                filetypes=[("JSONC files", "*.jsonc"), ("JSON files", "*.json"), ("All files", "*.*")],
                initialfile="differences.jsonc"
            )

            if output_path:
                # JSONC 형식으로 저장
                jsonc_content = format_as_jsonc(differences)

                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(jsonc_content)

                messagebox.showinfo(
                    "완료",
                    f"차이점이 성공적으로 저장되었습니다.\n\n저장 위치: {output_path}"
                )

        except json.JSONDecodeError as e:
            messagebox.showerror("오류", f"JSON 파싱 오류:\n{str(e)}")
        except Exception as e:
            messagebox.showerror("오류", f"파일 처리 중 오류 발생:\n{str(e)}")


def main():
    root = tk.Tk()
    app = JsoncDiffApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
