// The manual opens in the language the program is set to, unless the address names one (?lang=).
(function () {
  var body = document.body;
  if (body.dataset.explicit === '1') return;
  var lang = null;
  try { lang = JSON.parse(localStorage.getItem('pp-lang')); } catch (e) { /* storage blocked */ }
  if (!lang) lang = (navigator.language || 'en').toLowerCase().indexOf('it') === 0 ? 'it' : 'en';
  if ((lang === 'it' || lang === 'en') && lang !== body.dataset.lang) {
    location.replace('/manual?lang=' + lang + location.hash);
  }
})();
