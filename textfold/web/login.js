(() => {
  'use strict';
  const form = document.getElementById('login-form');
  const password = document.getElementById('password');
  const button = document.getElementById('login-submit');
  const error = document.getElementById('login-error');
  const toggle = document.getElementById('toggle-password');
  if (document.body.dataset.ready !== 'true') {
    form.hidden = true;
    document.getElementById('setup-note').hidden = false;
  }
  toggle.onclick = () => {
    const show = password.type === 'password';
    password.type = show ? 'text' : 'password';
    toggle.textContent = show ? '隐藏密码' : '显示密码';
    toggle.setAttribute('aria-pressed', String(show));
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    error.hidden = true; button.disabled = true; button.textContent = '正在登录…';
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: document.getElementById('username').value.trim(), password: password.value,
          next: new URLSearchParams(location.search).get('next') || '/' })
      });
      const result = await response.json();
      if (!response.ok) {
        const message = response.status === 429 ? '尝试次数过多，请稍后再试。' : response.status === 401 ? '账号或密码不正确，请重新输入。'
          : result.error === 'account-not-configured' ? '登录账号尚未初始化，请联系管理员。' : '暂时无法登录，请稍后重试。';
        throw new Error(message);
      }
      // The server validates the return path. Restrict it here too, before navigation.
      const target = new URL(result.next || '/', location.origin);
      location.replace(target.origin === location.origin ? target.href : '/');
    } catch (reason) {
      error.textContent = reason instanceof TypeError ? '无法连接阅读空间，请检查网络后重试。' : reason.message;
      error.hidden = false;
    } finally { button.disabled = false; button.textContent = '登录'; }
  };
})();
