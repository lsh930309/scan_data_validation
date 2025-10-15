// ==UserScript==
// @name         Gradio OCR Tool - State Persistence
// @namespace    http://tampermonkey.net/
// @version      4.0
// @description  Gradio 앱의 form_number, key_number, image_index 상태를 localStorage에 저장/복원
// @author       You
// @match        http://127.0.0.1:7860/*
// @match        http://localhost:7860/*
// @grant        none
// @run-at       document-end
// ==/UserScript==

(function() {
    'use strict';

    const STORAGE_KEY = 'gradio_ocr_state';
    const SAVE_DELAY = 500; // 저장 디바운스 (ms)

    let saveTimeout = null;
    let initialized = false;

    console.log('[Gradio State] Script loaded - v4.0');

    // elem_id를 사용한 명확한 selector
    function getFormDropdown() {
        const container = document.querySelector('#form_number_dropdown');
        return container ? container.querySelector('input') : null;
    }

    function getKeyDropdown() {
        const container = document.querySelector('#key_number_dropdown');
        return container ? container.querySelector('input') : null;
    }

    // 상태 저장
    function saveState() {
        try {
            const formInput = getFormDropdown();
            const keyInput = getKeyDropdown();

            const formValue = formInput ? formInput.value : null;
            const keyValue = keyInput ? keyInput.value : null;

            // Status label에서 current index 추출
            const statusElement = document.querySelector('#status_label');
            let currentIndex = 0;

            if (statusElement) {
                const statusText = statusElement.textContent || '';
                const match = statusText.match(/(\d+)\s*\/\s*(\d+)/);
                currentIndex = match ? parseInt(match[1]) - 1 : 0; // 0-based index
            }

            const state = {
                form_number: formValue,
                key_number: keyValue,
                current_index: currentIndex,
                timestamp: Date.now()
            };

            // 유효한 상태만 저장
            if (formValue || keyValue) {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
                console.log('[Gradio State] Saved:', state);
            }
        } catch (e) {
            console.error('[Gradio State] Save failed:', e);
        }
    }

    // 디바운스된 저장
    function debouncedSave() {
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(saveState, SAVE_DELAY);
    }

    // Input 값 설정 및 이벤트 트리거
    function setDropdownValue(input, value) {
        if (!input || !value) return false;

        // Gradio dropdown 값 설정
        input.click();
        input.focus();
        input.value = value;

        // 모든 이벤트 트리거
        ['input', 'change', 'blur'].forEach(eventType => {
            input.dispatchEvent(new Event(eventType, { bubbles: true }));
        });

        // Enter 키 시뮬레이션
        const enterEvent = new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true
        });
        input.dispatchEvent(enterEvent);

        console.log(`[Gradio State] Set dropdown value: ${value}`);
        return true;
    }

    // 상태 복원
    function restoreState() {
        try {
            const savedState = localStorage.getItem(STORAGE_KEY);
            if (!savedState) {
                console.log('[Gradio State] No saved state found');
                return false;
            }

            const state = JSON.parse(savedState);
            console.log('[Gradio State] Restoring:', state);

            // Form Number 설정
            const formInput = getFormDropdown();
            if (formInput && state.form_number) {
                console.log('[Gradio State] Setting Form Number:', state.form_number);
                setDropdownValue(formInput, state.form_number);

                // Key Number 설정 (Form이 로드된 후)
                setTimeout(() => {
                    const keyInput = getKeyDropdown();
                    if (keyInput && state.key_number) {
                        console.log('[Gradio State] Setting Key Number:', state.key_number);
                        setDropdownValue(keyInput, state.key_number);

                        // Image Index 복원 (Key가 로드된 후)
                        setTimeout(() => {
                            restoreImageIndex(state.current_index);
                        }, 2000);
                    }
                }, 2000);
            }

            return true;
        } catch (e) {
            console.error('[Gradio State] Restore failed:', e);
            return false;
        }
    }

    // 이미지 인덱스 복원
    function restoreImageIndex(targetIndex) {
        if (targetIndex <= 0) {
            console.log('[Gradio State] No index to restore');
            return;
        }

        const nextButton = document.querySelector('#next_button');
        if (!nextButton) {
            console.warn('[Gradio State] Next button not found');
            return;
        }

        console.log(`[Gradio State] Restoring to index ${targetIndex}...`);

        let currentIndex = 0;
        const clickInterval = setInterval(() => {
            if (currentIndex >= targetIndex) {
                clearInterval(clickInterval);
                console.log(`[Gradio State] ✓ Restored to index ${targetIndex}`);
                return;
            }

            nextButton.click();
            currentIndex++;
            console.log(`[Gradio State] Clicking next... (${currentIndex}/${targetIndex})`);
        }, 400);
    }

    // DOM 변화 감지하여 자동 저장
    function observeChanges() {
        const observer = new MutationObserver((mutations) => {
            const hasStatusChange = mutations.some(m =>
                m.target.id === 'status_label' ||
                m.target.closest('#status_label')
            );

            if (hasStatusChange) {
                debouncedSave();
            }
        });

        // Status label 감시
        const statusLabel = document.querySelector('#status_label');
        if (statusLabel) {
            observer.observe(statusLabel, {
                childList: true,
                subtree: true,
                characterData: true
            });
            console.log('[Gradio State] Observer attached to status_label');
        }

        // Dropdown input 감시
        const formInput = getFormDropdown();
        const keyInput = getKeyDropdown();

        if (formInput) {
            formInput.addEventListener('change', debouncedSave);
            formInput.addEventListener('blur', debouncedSave);
            console.log('[Gradio State] Listener attached to Form dropdown');
        }
        if (keyInput) {
            keyInput.addEventListener('change', debouncedSave);
            keyInput.addEventListener('blur', debouncedSave);
            console.log('[Gradio State] Listener attached to Key dropdown');
        }
    }

    // 버튼 클릭 이벤트 감지
    function attachButtonListeners() {
        const buttons = [
            '#prev_button', '#next_button',
            '#prev_key_button', '#next_key_button',
            '#prev_form_button', '#next_form_button',
            '#save_button'
        ];

        let attachedCount = 0;

        buttons.forEach(selector => {
            const button = document.querySelector(selector);
            if (button) {
                button.addEventListener('click', () => {
                    console.log(`[Gradio State] Button clicked: ${selector}`);
                    debouncedSave();
                });
                attachedCount++;
            }
        });

        console.log(`[Gradio State] Button listeners attached (${attachedCount}/${buttons.length})`);
    }

    // 초기화
    function init() {
        if (initialized) return;

        console.log('[Gradio State] Initializing...');

        // Gradio 앱이 완전히 로드될 때까지 대기
        const checkInterval = setInterval(() => {
            const formInput = getFormDropdown();
            const keyInput = getKeyDropdown();
            const statusLabel = document.querySelector('#status_label');

            if (formInput && keyInput && statusLabel) {
                clearInterval(checkInterval);

                console.log('[Gradio State] ✓ DOM elements found');
                console.log('  - Form dropdown:', formInput);
                console.log('  - Key dropdown:', keyInput);
                console.log('  - Status label:', statusLabel);

                // 상태 복원
                restoreState();

                // 변화 감지 시작
                setTimeout(() => {
                    observeChanges();
                    attachButtonListeners();
                    console.log('[Gradio State] ✓ Initialization complete');
                }, 2000);

                initialized = true;
            } else {
                console.log('[Gradio State] Waiting for DOM... (Form:', !!formInput, 'Key:', !!keyInput, 'Status:', !!statusLabel, ')');
            }
        }, 500);

        // 30초 타임아웃
        setTimeout(() => {
            if (!initialized) {
                clearInterval(checkInterval);
                console.error('[Gradio State] ✗ Initialization timeout - DOM elements not found');
                console.log('[Gradio State] Debug info:');
                console.log('  - #form_number_dropdown:', document.querySelector('#form_number_dropdown'));
                console.log('  - #key_number_dropdown:', document.querySelector('#key_number_dropdown'));
                console.log('  - #status_label:', document.querySelector('#status_label'));
            }
        }, 30000);
    }

    // 페이지 로드 시 초기화
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        setTimeout(init, 1000); // Gradio 로딩 대기
    }

    // 페이지 언로드 시 마지막 저장
    window.addEventListener('beforeunload', () => {
        console.log('[Gradio State] Page unloading, saving state...');
        saveState();
    });

    // 수동 명령어
    window.gradioState = {
        save: saveState,
        restore: restoreState,
        clear: () => {
            localStorage.removeItem(STORAGE_KEY);
            console.log('[Gradio State] State cleared');
        },
        get: () => {
            const state = localStorage.getItem(STORAGE_KEY);
            return state ? JSON.parse(state) : null;
        },
        debug: () => {
            console.log('=== Gradio State Debug ===');
            console.log('Form dropdown:', getFormDropdown());
            console.log('Key dropdown:', getKeyDropdown());
            console.log('Status label:', document.querySelector('#status_label'));
            console.log('Current state:', window.gradioState.get());
            console.log('Form container:', document.querySelector('#form_number_dropdown'));
            console.log('Key container:', document.querySelector('#key_number_dropdown'));
        }
    };

    console.log('[Gradio State] Commands: gradioState.save(), .restore(), .clear(), .get(), .debug()');
})();
