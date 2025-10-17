// ==UserScript==
// @name         Gradio OCR Helper - Simplified
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  OCR 텍스트박스 자동 선택 및 저장 후 포커스 해제 (간소화 버전)
// @author       You
// @match        http://127.0.0.1:7860/*
// @match        http://localhost:7860/*
// @match        http://127.0.0.1:*/
// @match        http://localhost:*/
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    console.log('✨ Gradio OCR Helper v2.0 시작');

    // ===== OCR 텍스트박스 자동 전체 선택 기능 =====
    const setupOcrTextboxAutoSelect = () => {
        // OCR 값 레이블을 가진 텍스트박스 찾기
        const findOcrTextbox = () => {
            const labels = Array.from(document.querySelectorAll('label'));
            for (const label of labels) {
                if (label.textContent.trim() === 'OCR 값') {
                    // Radio 버튼이 아닌 일반 텍스트 입력만
                    const container = label.closest('.block, .form, [class*="wrap"]');
                    if (container) {
                        const input = container.querySelector('input[type="text"], textarea');
                        // Radio 버튼 그룹 제외
                        if (input && !input.closest('[role="radiogroup"]')) {
                            return input;
                        }
                    }
                }
            }
            return null;
        };

        const attachSelectAllListener = () => {
            const ocrInput = findOcrTextbox();
            if (ocrInput && !ocrInput.dataset.selectAllAttached) {
                let hasBeenFocused = false;

                ocrInput.addEventListener('focus', (e) => {
                    if (!hasBeenFocused) {
                        // 약간의 지연 후 전체 선택 (Gradio 처리 완료 대기)
                        setTimeout(() => {
                            e.target.select();
                            console.log('✅ [Tampermonkey] OCR 텍스트 자동 선택 완료');
                        }, 10);
                    }
                    hasBeenFocused = true;
                });

                ocrInput.addEventListener('blur', () => {
                    hasBeenFocused = false;
                });

                ocrInput.dataset.selectAllAttached = 'true';
                console.log('✅ [Tampermonkey] OCR 텍스트박스 자동 선택 기능 활성화');
            }
        };

        // MutationObserver로 동적 생성 감지
        const observer = new MutationObserver(() => {
            attachSelectAllListener();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // 초기 설정
        attachSelectAllListener();
    };

    // ===== 저장 버튼 클릭 후 포커스 해제 =====
    const setupSaveButtonBlur = () => {
        const saveButton = document.getElementById('save_button');
        if (saveButton && !saveButton.dataset.blurAttached) {
            saveButton.addEventListener('click', () => {
                // 현재 포커스된 요소에서 포커스 제거
                if (document.activeElement) {
                    document.activeElement.blur();
                    console.log('✅ [Tampermonkey] 저장 후 포커스 해제 완료');
                }
            });
            saveButton.dataset.blurAttached = 'true';
            console.log('✅ [Tampermonkey] 저장 버튼 포커스 해제 기능 활성화');
        }
    };

    // ===== 초기화 =====
    const init = () => {
        // Gradio UI 로드 대기
        setTimeout(() => {
            setupOcrTextboxAutoSelect();
            setupSaveButtonBlur();
        }, 1000);

        // 주기적으로 체크 (동적 UI 변경 대응)
        setInterval(() => {
            setupSaveButtonBlur();
        }, 2000);
    };

    // DOM 로딩 완료 후 실행
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
