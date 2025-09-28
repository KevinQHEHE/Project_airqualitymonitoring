/**
 * add_user.js
 * Admin "Add User" page script.
 * Responsibilities:
 *  - Validate form inputs
 *  - Build payload matching backend admin API
 *  - Send POST /api/admin/users with Authorization header
 *  - Show inline success/error messages and redirect on success
 */
(function () {
  'use strict';

  function getAuthToken() {
    // Try the same keys other admin pages use: localStorage -> sessionStorage -> cookie
    try {
      return (
        localStorage.getItem('access_token') ||
        sessionStorage.getItem('access_token') ||
        (document.cookie.match(/(?:^|; )access_token=([^;]+)/) || [])[1] ||
        ''
      );
    } catch (e) {
      return '';
    }
  }

  function showAlert(type, message) {
    const alert = document.getElementById('formAlert');
    if (!alert) return;
    alert.className = 'alert';
    alert.classList.add(type === 'error' ? 'alert-danger' : 'alert-success');
    alert.textContent = message;
    alert.classList.remove('d-none');
  }

  function clearAlert() {
    const alert = document.getElementById('formAlert');
    if (!alert) return;
    alert.className = 'alert d-none';
    alert.textContent = '';
  }

  function validateForm(data) {
    const errors = [];
    if (!data.username || data.username.trim().length < 3) {
      errors.push('Tên đăng nhập phải có ít nhất 3 ký tự.');
    }
    if (!data.email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email)) {
      errors.push('Email không hợp lệ.');
    }
    if (!data.password || data.password.length < 8) {
      errors.push('Mật khẩu phải có ít nhất 8 ký tự.');
    }
    return errors;
  }

  async function submitForm(e) {
    e.preventDefault();
    clearAlert();

    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;

    const payload = {
      username: document.getElementById('username').value.trim(),
      email: document.getElementById('email').value.trim(),
      password: document.getElementById('password').value,
      role: document.getElementById('role').value,
      status: document.getElementById('status').value
    };

    const errors = validateForm(payload);
    if (errors.length > 0) {
      showAlert('error', errors.join(' '));
      submitBtn.disabled = false;
      return;
    }

    const token = getAuthToken();

    try {
      const res = await fetch('/api/admin/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': 'Bearer ' + token } : {})
        },
        body: JSON.stringify(payload)
      });

      if (res.status === 201 || res.status === 200) {
        showAlert('success', 'Tạo người dùng thành công. Chuyển hướng về danh sách...');
        setTimeout(() => {
          window.location.href = '/admin';
        }, 900);
        return;
      }

      // Try parse error response
      let errText = 'Có lỗi khi tạo người dùng.';
      try {
        const errJson = await res.json();
        if (errJson && errJson.error) errText = errJson.error;
        else if (errJson && errJson.message) errText = errJson.message;
      } catch (parseErr) {
        errText = `${res.status} ${res.statusText}`;
      }

      if (res.status === 401 || res.status === 403) {
        showAlert('error', 'Không có quyền. Hãy đăng nhập lại.');
        // optional: redirect to login after short delay
        setTimeout(() => { window.location.href = '/admin/login'; }, 1000);
      } else {
        showAlert('error', errText);
      }

    } catch (err) {
      console.error('Add user failed', err);
      showAlert('error', 'Lỗi mạng hoặc server. Vui lòng thử lại.');
    } finally {
      submitBtn.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('addUserForm');
    if (form) form.addEventListener('submit', submitForm);
  });

})();
