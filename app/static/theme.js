(() => {
  const storageKey = 'watcher-theme';
  const root = document.documentElement;
  const systemDark = window.matchMedia('(prefers-color-scheme: dark)');
  const savedTheme = localStorage.getItem(storageKey);

  const preferredTheme = () => {
    const saved = localStorage.getItem(storageKey);
    return saved === 'light' || saved === 'dark'
      ? saved
      : (systemDark.matches ? 'dark' : 'light');
  };

  const applyTheme = theme => {
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const dark = theme === 'dark';
      button.setAttribute('aria-label', dark ? 'Use light mode' : 'Use dark mode');
      button.setAttribute('title', dark ? 'Use light mode' : 'Use dark mode');
      button.setAttribute('aria-pressed', String(dark));
      const label = button.querySelector('[data-theme-label]');
      if (label) label.textContent = dark ? 'Light mode' : 'Dark mode';
      const icon = button.querySelector('[data-theme-icon]');
      if (icon) icon.textContent = dark ? '☀' : '☾';
    });
  };

  applyTheme(savedTheme === 'light' || savedTheme === 'dark' ? savedTheme : preferredTheme());

  document.addEventListener('DOMContentLoaded', () => {
    applyTheme(preferredTheme());
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem(storageKey, next);
        applyTheme(next);
      });
    });
  });

  systemDark.addEventListener('change', () => {
    if (!localStorage.getItem(storageKey)) applyTheme(preferredTheme());
  });
})();
