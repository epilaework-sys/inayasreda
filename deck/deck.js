/* ==========================================================================
   Управление деком.

   Навигация под кликер: стрелки, пробел, PageUp/PageDown.
   Прыжок на слайд — набрать номер и Enter (на случай, если тайминг поплывёт).
   ?print — раскладка для PDF: каждый шаг анимации отдельной страницей.
   ========================================================================== */

(function () {
  'use strict';

  // Звезда вшита в скрипт, а не подгружается файлом: дек должен работать
  // с file:// без единого сетевого запроса.
  var STAR =
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 54.374 54.41" fill="currentColor" aria-hidden="true">' +
    '<path d="M 54.374,28.712 L 54.374,26.016 L 48.949,26.016 C 45.709,26.016 42.761,26.016 39.133,26.007 C 37.242,26.003 35.476,25.487 33.886,24.477 C 30.489,22.319 28.749,19.237 28.711,15.318 C 28.678,11.81 28.685,8.929 28.693,5.815 L 28.7,0.0 L 25.989,0.0 L 25.99,4.871 C 25.992,8.272 25.993,11.296 25.98,15.07 C 25.977,15.78 25.914,16.502 25.793,17.217 C 25.346,19.839 24.024,22.035 21.86,23.743 C 19.901,25.291 17.628,26.042 15.014,26.023 C 11.507,26.008 8.648,26.009 5.534,26.013 L 0.0,26.016 L 0.0,28.712 L 5.214,28.713 C 8.497,28.711 11.461,28.713 15.128,28.709 L 15.143,28.709 C 16.293,28.709 17.349,28.86 18.371,29.168 C 22.903,30.537 26.039,34.833 25.998,39.615 C 25.968,43.012 25.975,45.779 25.982,48.784 L 25.989,54.41 L 28.701,54.41 L 28.698,48.781 C 28.696,45.69 28.694,42.852 28.706,39.37 C 28.717,36.412 29.807,33.852 31.946,31.761 C 34.005,29.75 36.508,28.726 39.387,28.717 C 42.9,28.704 45.756,28.708 48.877,28.71 Z"/></svg>';

  var viewport = document.getElementById('viewport');
  var jumpBox = document.getElementById('jump');
  var slides = [].slice.call(document.querySelectorAll('.stage'));
  var printMode = /[?&]print/.test(location.search);

  /* ---------- Светлая тема ------------------------------------------------ */

  // Всё, что можно, светлая тема делает переменными в theme-light.css.
  // Здесь остаётся только растр: у логотипа и QR под светлый фон нужны
  // отдельные файлы, переменными их не перекрасить.
  if (/[?&]light/.test(location.search)) {
    document.body.classList.add('light');
    var swap = { 'logo-dark.png': 'logo-light.png', 'qr-site.png': 'qr-site-light.png' };
    [].forEach.call(document.images, function (img) {
      var file = img.getAttribute('src');
      if (!swap[file]) return;
      // Фото на вылет, чёрный экран и заставка остаются тёмными и в светлой
      // теме — растр на них подменять нельзя, иначе логотип и QR потеряются
      // на собственном фоне.
      var stage = img.closest('.stage');
      if (stage && (stage.classList.contains('blackout') ||
                    stage.querySelector('.bleed, .videoslot'))) return;
      img.setAttribute('src', swap[file]);
    });
  }

  function paintStars(root) {
    [].forEach.call(root.querySelectorAll('.star'), function (el) {
      if (!el.firstChild) el.innerHTML = STAR;
    });
  }
  paintStars(document);

  // Номера слайдов проставляются из порядка в разметке, чтобы нумерация
  // не расходилась с сценарием при правках.
  slides.forEach(function (slide, i) {
    if (slide.dataset.bare === 'true') return;
    var tag = document.createElement('div');
    tag.className = 'slide-no';
    tag.textContent = String(i + 1).padStart(2, '0');
    slide.appendChild(tag);
  });

  function stepsOf(slide) {
    var groups = {};
    [].forEach.call(slide.querySelectorAll('.step'), function (el) {
      var n = parseInt(el.dataset.step || '1', 10);
      (groups[n] = groups[n] || []).push(el);
    });
    return Object.keys(groups)
      .map(Number)
      .sort(function (a, b) { return a - b; })
      .map(function (n) { return groups[n]; });
  }

  /* ---------- Режим печати: разворачиваем шаги в отдельные страницы ------- */

  if (printMode) {
    document.body.classList.add('printing');
    var pages = document.createDocumentFragment();
    slides.forEach(function (slide) {
      var total = stepsOf(slide).length;
      for (var k = 0; k <= total; k++) {
        var copy = slide.cloneNode(true);
        copy.classList.add('current');
        var groups = stepsOf(copy);
        groups.forEach(function (group, gi) {
          group.forEach(function (el) {
            el.classList.toggle('on', gi < k);
          });
        });
        if (total > 0 && k === 0) {
          // Первая страница слайда — состояние до первого появления.
          // Если на слайде вообще нет статики, страница пустая — пропускаем.
          var hasStatic = copy.querySelector('.pad, .split, .bleed, .logo');
          if (!hasStatic) continue;
        }
        pages.appendChild(copy);
      }
    });
    viewport.innerHTML = '';
    viewport.appendChild(pages);
    paintStars(viewport);
    return;
  }

  /* ---------- Обычный режим показа ---------------------------------------- */

  function fit() {
    var s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    slides.forEach(function (slide) {
      slide.style.transform = 'scale(' + s + ')';
    });
  }
  window.addEventListener('resize', fit);
  fit();

  var index = 0;
  var step = 0;
  var steps = [];

  // Видео на слайде должно начинаться с первого кадра в тот момент, когда
  // спикер до него дошёл, а не доигрывать начатое в фоне.
  function syncVideo() {
    slides.forEach(function (slide, i) {
      [].forEach.call(slide.querySelectorAll('video'), function (v) {
        if (i === index) {
          if (v.paused) { try { v.currentTime = 0; } catch (e) {} }
          var p = v.play();
          if (p && p.catch) p.catch(function () {});
        } else {
          v.pause();
        }
      });
    });
  }

  function render() {
    slides.forEach(function (slide, i) {
      slide.classList.toggle('current', i === index);
    });
    syncVideo();
    steps = stepsOf(slides[index]);
    steps.forEach(function (group, gi) {
      group.forEach(function (el) { el.classList.toggle('on', gi < step); });
    });
    location.hash = String(index + 1);
  }

  function go(i, atEnd) {
    index = Math.max(0, Math.min(slides.length - 1, i));
    steps = stepsOf(slides[index]);
    step = atEnd ? steps.length : 0;
    render();
  }

  function forward() {
    if (step < steps.length) { step++; render(); }
    else if (index < slides.length - 1) { go(index + 1); }
  }

  function back() {
    if (step > 0) { step--; render(); }
    else if (index > 0) { go(index - 1, true); }
  }

  var typed = '';
  var typedTimer = null;

  function showTyped() {
    jumpBox.textContent = typed ? 'СЛАЙД ' + typed : '';
    jumpBox.classList.toggle('on', !!typed);
    clearTimeout(typedTimer);
    typedTimer = setTimeout(function () {
      typed = '';
      jumpBox.classList.remove('on');
    }, 2200);
  }

  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    if (e.key >= '0' && e.key <= '9') {
      typed = (typed + e.key).slice(0, 2);
      showTyped();
      e.preventDefault();
      return;
    }
    if (e.key === 'Enter') {
      if (typed) {
        go(parseInt(typed, 10) - 1);
        typed = '';
        jumpBox.classList.remove('on');
      }
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape') {
      typed = '';
      jumpBox.classList.remove('on');
      return;
    }

    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
      case ' ':
      case 'PageDown':
        forward(); e.preventDefault(); break;
      case 'ArrowLeft':
      case 'ArrowUp':
      case 'PageUp':
        back(); e.preventDefault(); break;
      case 'Home':
        go(0); e.preventDefault(); break;
      case 'End':
        go(slides.length - 1, true); e.preventDefault(); break;
      case 'f':
      case 'F':
        if (document.fullscreenElement) document.exitFullscreen();
        else document.documentElement.requestFullscreen();
        break;
    }
  });

  // ?all — открыть слайд со всеми раскрытыми шагами.
  // Нужно для съёмки превью и для проверки вёрстки в конечном состоянии.
  var showAll = /[?&]all/.test(location.search);
  var start = parseInt((location.hash || '').replace('#', ''), 10);
  go(isNaN(start) ? 0 : start - 1, showAll);
})();
