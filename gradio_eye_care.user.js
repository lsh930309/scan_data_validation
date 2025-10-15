// ==UserScript==
// @name         Gradio Eye Care - 이미지 뷰어 눈보호
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Gradio 다크모드에서 흰색 스캔 이미지로 인한 눈부심 방지 (부드러운 전환 + 밝기 조절)
// @author       You
// @match        http://127.0.0.1:7860/*
// @match        http://localhost:7860/*
// @match        http://127.0.0.1:*/
// @match        http://localhost:*/
// @grant        GM_addStyle
// @grant        GM_getValue
// @grant        GM_setValue
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    // ===== 설정 값 (GM_getValue/setValue로 저장) =====
    const CONFIG = {
        brightness: GM_getValue('brightness', 0.75),      // 밝기 (0.0 ~ 1.0)
        contrast: GM_getValue('contrast', 1.0),           // 대비 (0.0 ~ 2.0)
        transitionSpeed: GM_getValue('transitionSpeed', 200), // 전환 속도 (ms)
        enableFilter: GM_getValue('enableFilter', true),  // 필터 활성화
        overlayColor: GM_getValue('overlayColor', 'rgba(0, 0, 0, 0.2)'), // 오버레이 색상

        // 키다운 매크로 설정
        enableMacro: GM_getValue('enableMacro', false),   // 매크로 활성화
        macroInterval: GM_getValue('macroInterval', 0.3)  // 자동 입력 간격 (초)
    };

    // ===== CSS 스타일 주입 =====
    const injectStyles = () => {
        GM_addStyle(`
            /* ========== Gradio 로딩 인디케이터 완전 차단 ========== */

            /* 방법 1: 로딩 요소를 투명하게 만들기 (덮어버리기) */
            .loading,
            .loader,
            .pending,
            [class*="loading"],
            [class*="pending"],
            .wrap.pending,
            .wrap.generating,
            .gradio-container .loader,
            .gradio-container .loading,
            div.pending,
            div.loading {
                background: transparent !important;
                opacity: 0 !important;
                visibility: hidden !important;
                pointer-events: none !important;
            }

            /* 방법 2: absolute 포지션 오버레이를 완전히 제거 */
            div[style*="position: absolute"] > svg,
            div[style*="position: absolute"][style*="z-index"] {
                display: none !important;
            }

            /* 방법 3: 주황색 스피너 SVG를 강제로 숨김 */
            svg,
            svg.spinner,
            svg[class*="spinner"],
            svg[class*="loading"],
            svg[class*="icon"] {
                opacity: 0 !important;
            }

            /* 단, 일반 아이콘은 표시 (버튼 등) */
            button svg,
            .icon-button svg {
                opacity: 1 !important;
            }

            /* 방법 4: Gradio 내부 로딩 상태 클래스 무력화 */
            .svelte-* .loading,
            .svelte-* .pending,
            [class^="svelte-"] .loading,
            [class^="svelte-"] .pending {
                display: none !important;
            }

            /* 방법 5: 로딩 중일 때 배경색을 어둡게 유지 */
            .image-container.loading,
            [data-testid="image"].loading,
            .image-container.pending,
            [data-testid="image"].pending {
                background-color: #1a1a1a !important;
            }

            /* 방법 6: 이미지 컨테이너 위에 투명 보호막 생성 */
            .image-container::before,
            [data-testid="image"]::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: #1a1a1a;
                opacity: 0;
                pointer-events: none;
                z-index: 9999;
                transition: opacity 0.3s ease;
            }

            /* 로딩 중일 때는 보호막 활성화 */
            .image-container.loading::before,
            [data-testid="image"].loading::before,
            .image-container.pending::before,
            [data-testid="image"].pending::before {
                opacity: 1 !important;
            }

            /* ========== 이미지 뷰어 부드러운 전환 ========== */
            /* 이미지 컨테이너 부드러운 전환 */
            .image-container img,
            [data-testid="image"] img,
            img[alt="이미지"] {
                transition: opacity ${CONFIG.transitionSpeed}ms ease-in-out,
                            filter ${CONFIG.transitionSpeed}ms ease-in-out !important;
            }

            /* 이미지 로딩 중 깜빡임 방지 */
            .image-container,
            [data-testid="image"] {
                background-color: #1a1a1a !important;
                position: relative;
            }

            /* 이미지 필터 적용 */
            .eye-care-filter {
                filter: brightness(${CONFIG.brightness}) contrast(${CONFIG.contrast}) !important;
                position: relative;
            }

            /* 오버레이 레이어 (추가 눈부심 감소) */
            .eye-care-overlay::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: ${CONFIG.overlayColor};
                pointer-events: none;
                z-index: 1;
            }

            /* 설정 패널 스타일 */
            #eye-care-settings {
                position: fixed;
                top: 10px;
                right: 10px;
                background: #2d2d2d;
                border: 1px solid #444;
                border-radius: 8px;
                padding: 15px;
                z-index: 9999;
                color: #fff;
                font-family: monospace;
                font-size: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                max-width: 280px;
                display: none;
            }

            #eye-care-settings.show {
                display: block;
            }

            #eye-care-settings h3 {
                margin: 0 0 10px 0;
                font-size: 14px;
                border-bottom: 1px solid #555;
                padding-bottom: 5px;
            }

            #eye-care-settings label {
                display: block;
                margin: 10px 0 5px 0;
                font-size: 11px;
                color: #aaa;
            }

            #eye-care-settings input[type="range"] {
                width: 100%;
                margin: 5px 0;
            }

            #eye-care-settings input[type="checkbox"] {
                margin-right: 5px;
            }

            #eye-care-settings .value-display {
                display: inline-block;
                background: #1a1a1a;
                padding: 2px 6px;
                border-radius: 3px;
                margin-left: 5px;
                color: #ffdd57;
            }

            #eye-care-settings button {
                background: #ffdd57;
                border: none;
                padding: 5px 10px;
                border-radius: 4px;
                cursor: pointer;
                margin: 5px 5px 0 0;
                font-size: 11px;
                color: #000;
            }

            #eye-care-settings button:hover {
                background: #ffd700;
            }

            /* 토글 버튼 */
            #eye-care-toggle {
                position: fixed;
                top: 10px;
                right: 10px;
                background: #ffdd57;
                border: none;
                padding: 8px 12px;
                border-radius: 6px;
                cursor: pointer;
                z-index: 10000;
                font-size: 12px;
                font-weight: bold;
                color: #000;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            }

            #eye-care-toggle:hover {
                background: #ffd700;
            }
        `);
    };

    // ===== 설정 UI 생성 =====
    const createSettingsPanel = () => {
        const panel = document.createElement('div');
        panel.id = 'eye-care-settings';
        panel.innerHTML = `
            <h3>👁️ 눈 보호 설정</h3>

            <label>
                <input type="checkbox" id="enable-filter" ${CONFIG.enableFilter ? 'checked' : ''}>
                필터 활성화
            </label>

            <label>
                밝기 <span class="value-display" id="brightness-value">${CONFIG.brightness}</span>
                <input type="range" id="brightness-slider" min="0.3" max="1.0" step="0.05" value="${CONFIG.brightness}">
            </label>

            <label>
                대비 <span class="value-display" id="contrast-value">${CONFIG.contrast}</span>
                <input type="range" id="contrast-slider" min="0.5" max="1.5" step="0.05" value="${CONFIG.contrast}">
            </label>

            <label>
                전환 속도 <span class="value-display" id="speed-value">${CONFIG.transitionSpeed}ms</span>
                <input type="range" id="speed-slider" min="50" max="500" step="50" value="${CONFIG.transitionSpeed}">
            </label>

            <label>
                오버레이 투명도
                <input type="range" id="overlay-slider" min="0" max="0.5" step="0.05" value="0.2">
            </label>

            <hr style="border: none; border-top: 1px solid #555; margin: 15px 0;">
            <h4 style="margin: 10px 0 5px 0; font-size: 12px;">⌨️ 자동 넘기기 매크로</h4>

            <label>
                <input type="checkbox" id="enable-macro" ${CONFIG.enableMacro ? 'checked' : ''}>
                매크로 활성화
            </label>

            <div style="background: #1a1a1a; padding: 8px; border-radius: 4px; margin: 8px 0; font-size: 10px; line-height: 1.4;">
                <strong>사용법:</strong><br>
                • 시작: <code>Ctrl + ← / →</code><br>
                • 중지: <code>반대 방향키</code> 누르기
            </div>

            <label>
                자동 입력 간격 <span class="value-display" id="interval-value">${CONFIG.macroInterval}초</span>
                <input type="range" id="interval-slider" min="0.1" max="2.0" step="0.1" value="${CONFIG.macroInterval}">
            </label>

            <button id="apply-settings">적용</button>
            <button id="reset-settings">초기화</button>
            <button id="close-settings">닫기</button>
        `;
        document.body.appendChild(panel);

        // 토글 버튼 생성
        const toggleBtn = document.createElement('button');
        toggleBtn.id = 'eye-care-toggle';
        toggleBtn.textContent = '👁️ 설정';
        document.body.appendChild(toggleBtn);

        // 이벤트 리스너
        toggleBtn.addEventListener('click', () => {
            panel.classList.toggle('show');
        });

        document.getElementById('close-settings').addEventListener('click', () => {
            panel.classList.remove('show');
        });

        // 실시간 값 표시
        document.getElementById('brightness-slider').addEventListener('input', (e) => {
            document.getElementById('brightness-value').textContent = e.target.value;
        });
        document.getElementById('contrast-slider').addEventListener('input', (e) => {
            document.getElementById('contrast-value').textContent = e.target.value;
        });
        document.getElementById('speed-slider').addEventListener('input', (e) => {
            document.getElementById('speed-value').textContent = e.target.value + 'ms';
        });
        document.getElementById('interval-slider').addEventListener('input', (e) => {
            document.getElementById('interval-value').textContent = e.target.value + '초';
        });

        // 적용 버튼
        document.getElementById('apply-settings').addEventListener('click', () => {
            CONFIG.brightness = parseFloat(document.getElementById('brightness-slider').value);
            CONFIG.contrast = parseFloat(document.getElementById('contrast-slider').value);
            CONFIG.transitionSpeed = parseInt(document.getElementById('speed-slider').value);
            CONFIG.enableFilter = document.getElementById('enable-filter').checked;

            const overlayAlpha = parseFloat(document.getElementById('overlay-slider').value);
            CONFIG.overlayColor = `rgba(0, 0, 0, ${overlayAlpha})`;

            // 매크로 설정
            CONFIG.enableMacro = document.getElementById('enable-macro').checked;
            CONFIG.macroInterval = parseFloat(document.getElementById('interval-slider').value);

            // 저장
            GM_setValue('brightness', CONFIG.brightness);
            GM_setValue('contrast', CONFIG.contrast);
            GM_setValue('transitionSpeed', CONFIG.transitionSpeed);
            GM_setValue('enableFilter', CONFIG.enableFilter);
            GM_setValue('overlayColor', CONFIG.overlayColor);
            GM_setValue('enableMacro', CONFIG.enableMacro);
            GM_setValue('macroInterval', CONFIG.macroInterval);

            // 즉시 재적용
            location.reload();
        });

        // 초기화 버튼
        document.getElementById('reset-settings').addEventListener('click', () => {
            GM_setValue('brightness', 0.75);
            GM_setValue('contrast', 1.0);
            GM_setValue('transitionSpeed', 200);
            GM_setValue('enableFilter', true);
            GM_setValue('overlayColor', 'rgba(0, 0, 0, 0.2)');
            GM_setValue('enableMacro', false);
            GM_setValue('macroInterval', 0.3);
            location.reload();
        });
    };

    // ===== 이미지 요소에 필터 적용 =====
    const applyFilterToImages = () => {
        // Gradio 이미지 컨테이너 선택자 (여러 버전 대응)
        const selectors = [
            '[data-testid="image"] img',
            '.image-container img',
            'img[alt="이미지"]',
            '.gradio-image img'
        ];

        selectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(img => {
                if (CONFIG.enableFilter) {
                    img.classList.add('eye-care-filter');
                    // 오버레이는 부모 요소에 적용
                    if (img.parentElement) {
                        img.parentElement.classList.add('eye-care-overlay');
                    }
                } else {
                    img.classList.remove('eye-care-filter');
                    if (img.parentElement) {
                        img.parentElement.classList.remove('eye-care-overlay');
                    }
                }
            });
        });
    };

    // ===== 로딩 인디케이터 강제 제거 및 덮어버리기 =====
    const removeLoadingIndicators = () => {
        // 방법 1: 모든 로딩 관련 요소를 완전히 투명하게 만들기
        const loadingSelectors = [
            '.loading',
            '.loader',
            '.pending',
            '[class*="loading"]',
            '[class*="pending"]',
            '.wrap.generating',
            '.wrap.pending',
            'div.pending',
            'div.loading'
        ];

        loadingSelectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(element => {
                element.style.setProperty('display', 'none', 'important');
                element.style.setProperty('opacity', '0', 'important');
                element.style.setProperty('visibility', 'hidden', 'important');
                element.style.setProperty('pointer-events', 'none', 'important');
                element.style.setProperty('background', 'transparent', 'important');
            });
        });

        // 방법 2: 모든 SVG 스피너 제거 (주황색 회전 아이콘)
        document.querySelectorAll('svg').forEach(svg => {
            // 버튼 내부 아이콘은 제외
            if (!svg.closest('button') && !svg.closest('.icon-button')) {
                const parent = svg.parentElement;
                // absolute positioned div 내부의 svg는 로딩 스피너로 간주
                if (parent &&
                    (parent.style.position === 'absolute' ||
                     svg.classList.toString().includes('spin') ||
                     svg.classList.toString().includes('loading'))) {
                    svg.style.setProperty('display', 'none', 'important');
                    svg.style.setProperty('opacity', '0', 'important');
                }
            }
        });

        // 방법 3: position:absolute이고 z-index가 높은 오버레이 제거
        document.querySelectorAll('div').forEach(div => {
            const style = window.getComputedStyle(div);
            const isOverlay = style.position === 'absolute' &&
                            (style.inset === '0px' ||
                             (style.top === '0px' && style.left === '0px' &&
                              style.right === '0px' && style.bottom === '0px'));

            if (isOverlay) {
                const hasSpinner = div.querySelector('svg');
                const hasHighZIndex = parseInt(style.zIndex) > 100;

                if (hasSpinner || hasHighZIndex) {
                    div.style.setProperty('display', 'none', 'important');
                    div.style.setProperty('opacity', '0', 'important');
                }
            }
        });

        // 방법 4: 이미지 컨테이너에 어두운 보호막 강제 생성
        document.querySelectorAll('.image-container, [data-testid="image"]').forEach(container => {
            if (container.classList.contains('loading') || container.classList.contains('pending')) {
                // 이미 보호막이 있는지 확인
                let shield = container.querySelector('.eye-care-loading-shield');
                if (!shield) {
                    shield = document.createElement('div');
                    shield.className = 'eye-care-loading-shield';
                    shield.style.cssText = `
                        position: absolute !important;
                        top: 0 !important;
                        left: 0 !important;
                        right: 0 !important;
                        bottom: 0 !important;
                        background: #1a1a1a !important;
                        z-index: 9999 !important;
                        pointer-events: none !important;
                    `;
                    container.style.position = 'relative';
                    container.appendChild(shield);
                }
            }
        });
    };

    // ===== MutationObserver로 동적 이미지 감지 + 로딩 제거 =====
    const observeImageChanges = () => {
        const observer = new MutationObserver((mutations) => {
            let needsUpdate = false;

            mutations.forEach(mutation => {
                if (mutation.addedNodes.length > 0 ||
                    mutation.type === 'attributes' && mutation.attributeName === 'src') {
                    needsUpdate = true;
                }

                // 새로 추가된 노드 중 로딩 인디케이터가 있으면 즉시 제거
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === 1) { // Element 노드인 경우
                        // 로딩 클래스 체크
                        if (node.classList &&
                            (node.classList.contains('loading') ||
                             node.classList.contains('loader') ||
                             node.classList.contains('pending'))) {
                            node.style.display = 'none';
                        }

                        // SVG 스피너 체크
                        if (node.tagName === 'svg' &&
                            (node.classList.contains('spinner') ||
                             node.getAttribute('class')?.includes('spinner'))) {
                            node.style.display = 'none';
                        }

                        // 자식 요소 중 로딩 인디케이터 찾기
                        if (node.querySelectorAll) {
                            removeLoadingIndicators();
                        }
                    }
                });
            });

            if (needsUpdate) {
                // 디바운싱 (100ms)
                clearTimeout(window.eyeCareUpdateTimer);
                window.eyeCareUpdateTimer = setTimeout(() => {
                    applyFilterToImages();
                    removeLoadingIndicators();
                }, 100);
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['src', 'class', 'style']
        });
    };

    // ===== 키다운 매크로 시스템 (Ctrl + 좌/우 방향키) =====
    let macroState = {
        isActive: false,        // 매크로 실행 중
        intervalTimer: null,    // 자동 입력 인터벌
        currentDirection: null  // 현재 방향 ('left' or 'right')
    };

    const setupKeyMacro = () => {
        if (!CONFIG.enableMacro) return;

        // 키 다운 이벤트
        document.addEventListener('keydown', (e) => {
            // 텍스트 입력창에서는 매크로 비활성화
            if (e.target.nodeName === "INPUT" || e.target.nodeName === "TEXTAREA") return;

            // Ctrl + 좌/우 방향키 조합 감지
            if (e.ctrlKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
                e.preventDefault(); // 브라우저 기본 동작 방지

                const direction = e.key === 'ArrowLeft' ? 'left' : 'right';

                // 이미 같은 방향으로 실행 중이면 무시
                if (macroState.isActive && macroState.currentDirection === direction) {
                    return;
                }

                // 다른 방향이면 기존 매크로 중지 후 새로 시작
                if (macroState.isActive) {
                    stopMacro();
                }

                startMacro(direction);
                return;
            }

            // 매크로 실행 중일 때 반대 방향키 단독 입력으로 중지
            if (macroState.isActive && !e.ctrlKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
                const pressedDirection = e.key === 'ArrowLeft' ? 'left' : 'right';

                // 현재 실행 중인 방향과 반대 방향이면 매크로 중지
                if (pressedDirection !== macroState.currentDirection) {
                    e.preventDefault(); // 기본 동작 방지 (Gradio의 원래 단축키 동작 방지)
                    stopMacro();
                    console.log(`[Eye Care] 반대 방향키로 매크로 중지: ${pressedDirection}`);
                }
            }
        });
    };

    const startMacro = (direction) => {
        console.log(`[Eye Care] 자동 넘기기 시작: ${direction}`);
        macroState.isActive = true;
        macroState.currentDirection = direction;

        // 버튼 ID 결정
        const buttonId = direction === 'left' ? 'prev_button' : 'next_button';

        // 첫 클릭은 즉시 실행
        const button = document.getElementById(buttonId);
        if (button) button.click();

        // 설정된 간격으로 버튼 클릭
        macroState.intervalTimer = setInterval(() => {
            const button = document.getElementById(buttonId);
            if (button) {
                button.click();
                console.log(`[Eye Care] 자동 클릭: ${buttonId}`);
            }
        }, CONFIG.macroInterval * 1000);
    };

    const stopMacro = () => {
        if (macroState.intervalTimer) {
            clearInterval(macroState.intervalTimer);
            macroState.intervalTimer = null;
            console.log('[Eye Care] 자동 넘기기 중지');
        }

        macroState.isActive = false;
        macroState.currentDirection = null;
    };

    // ===== OCR 텍스트박스 첫 클릭 시 전체 선택 =====
    const setupOcrTextboxAutoSelect = () => {
        // OCR 텍스트박스 찾기
        const findOcrTextbox = () => {
            const labels = Array.from(document.querySelectorAll('label'));
            for (const label of labels) {
                if (label.textContent.trim() === 'OCR 값') {
                    const container = label.closest('.block, .form, [class*="container"]');
                    if (container) {
                        const input = container.querySelector('input[type="text"], textarea');
                        // Radio 버튼 그룹이 아닌 경우만
                        if (input && !input.closest('.radio-group, [role="radiogroup"]')) {
                            return input;
                        }
                    }
                }
            }
            return null;
        };

        const attachSelectAllListener = () => {
            const ocrInput = findOcrTextbox();

            if (ocrInput) {
                // 이미 리스너가 설정되었는지 확인
                if (ocrInput.dataset.selectAllAttached) {
                    return;
                }

                let hasBeenFocused = false;

                ocrInput.addEventListener('focus', (e) => {
                    if (!hasBeenFocused) {
                        // 약간의 지연을 두고 전체 선택 (Gradio의 포커스 처리 후)
                        setTimeout(() => {
                            e.target.select();
                        }, 10);
                    }
                    hasBeenFocused = true;
                });

                ocrInput.addEventListener('blur', () => {
                    hasBeenFocused = false;
                });

                // 리스너 설정 완료 표시
                ocrInput.dataset.selectAllAttached = 'true';
                console.log('✅ OCR 텍스트박스 자동 선택 기능 활성화');
            }
        };

        // MutationObserver로 동적 생성된 텍스트박스도 감지
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

    // ===== 초기화 =====
    const init = () => {
        injectStyles();

        // DOM 로딩 완료 후 실행
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                createSettingsPanel();
                applyFilterToImages();
                removeLoadingIndicators();
                observeImageChanges();
                setupKeyMacro(); // 키다운 매크로 활성화
                setupOcrTextboxAutoSelect(); // OCR 텍스트박스 자동 선택
            });
        } else {
            createSettingsPanel();
            applyFilterToImages();
            removeLoadingIndicators();
            observeImageChanges();
            setupKeyMacro(); // 키다운 매크로 활성화
            setupOcrTextboxAutoSelect(); // OCR 텍스트박스 자동 선택
        }

        // 주기적으로 필터 재적용 및 로딩 제거 (Gradio의 동적 렌더링 대응)
        setInterval(() => {
            applyFilterToImages();
            removeLoadingIndicators();
        }, 100); // 100ms마다 빠르게 체크

        // 추가: 더 공격적으로 로딩 제거 (50ms 간격)
        setInterval(() => {
            removeLoadingIndicators();
        }, 50);
    };

    init();
})();
