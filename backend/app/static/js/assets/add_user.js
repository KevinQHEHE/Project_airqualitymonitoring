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

    // Username
    if (!data.username || data.username.trim() === '') {
      errors.push('Vui lòng nhập tên đăng nhập.');
    } else if (data.username.trim().length < 3) {
      errors.push('Tên đăng nhập phải có ít nhất 3 ký tự.');
    }

    // Email
    if (!data.email || data.email.trim() === '') {
      errors.push('Vui lòng nhập email.');
    } else {
      const email = data.email.trim();
      // Basic validation - require an @ and a domain part
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
        errors.push('Email không hợp lệ. Vui lòng nhập email hợp lệ (ví dụ: user@gmail.com).');
      }
    }

    // Password
    if (!data.password || data.password === '') {
      errors.push('Vui lòng nhập mật khẩu.');
    } else if (data.password.length < 8) {
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
      // Force role to 'user' to prevent creation of admin accounts from this form.
      role: 'user',
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
      // Default message
      let errText = 'Có lỗi khi tạo người dùng.';
      let errJson = null;
      try {
        errJson = await res.json();
        // Server might return structured field errors
        if (errJson) {
          // If backend returns { errors: { field: 'msg' } }
          if (errJson.errors && typeof errJson.errors === 'object') {
            const fieldMsgs = [];
            for (const k of Object.keys(errJson.errors)) {
              fieldMsgs.push(errJson.errors[k]);
            }
            errText = fieldMsgs.join(' ');
          } else if (errJson.error) {
            errText = errJson.error;
          } else if (errJson.message) {
            errText = errJson.message;
          } else if (typeof errJson === 'string') {
            errText = errJson;
          }

          // Common Mongo duplicate key or backend message heuristics (set errText but we will
          // choose which field to show below prioritizing username then email)
          if (/duplicate|unique|E11000/i.test(JSON.stringify(errJson))) {
            if (/username/i.test(JSON.stringify(errJson))) {
              errText = 'Trùng tên đăng nhập. Vui lòng chọn tên khác.';
            } else if (/email/i.test(JSON.stringify(errJson))) {
              errText = 'Trùng email. Vui lòng sử dụng email khác.';
            } else {
              errText = 'Dữ liệu trùng lặp. Vui lòng kiểm tra các trường nhập.';
            }
          }

          // Weak password heuristic: map common server messages to friendly text
          if (/weak[_\- ]?password|password[_\s]?too[_\s]?weak|weak password/i.test(JSON.stringify(errJson)) ) {
            errText = 'Mật khẩu còn yếu, vui lòng nhập lại mật khẩu với độ mạnh cao hơn.';
          }
        }
      } catch (parseErr) {
        errText = `${res.status} ${res.statusText}`;
      }

      if (res.status === 401 || res.status === 403) {
        showAlert('error', 'Không có quyền. Hãy đăng nhập lại.');
        // optional: redirect to login after short delay
        setTimeout(() => { window.location.href = '/admin/login'; }, 1000);
      } else if (res.status === 409) {
        // Conflict: show a generic collision message to avoid revealing which field
        // specifically caused the conflict and to prevent race-condition confusion.
        showAlert('error', 'Tên đăng nhập hoặc email đã có trên hệ thống. Vui lòng kiểm tra và thử lại.');
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

    // Password visibility toggle (inverted logic):
    // - default: hidden (input.type === 'password') -> icon = fa-eye-slash
    // - visible: input.type === 'text' -> icon = fa-eye
    try {
      const toggleBtn = document.getElementById('togglePassword');
      const pwdInput = document.getElementById('password');
      const icon = document.getElementById('togglePasswordIcon');
      if (toggleBtn && pwdInput && icon) {
        // initialize attributes to match the DOM (closed-eye = hidden)
        toggleBtn.setAttribute('aria-pressed', 'false');
        toggleBtn.title = 'Hiển thị mật khẩu';

        toggleBtn.addEventListener('click', function () {
          const isCurrentlyHidden = pwdInput.type === 'password';
          if (isCurrentlyHidden) {
            // show
            pwdInput.type = 'text';
            icon.classList.remove('fa-eye-slash');
            icon.classList.add('fa-eye');
            toggleBtn.setAttribute('aria-pressed', 'true');
            toggleBtn.title = 'Ẩn mật khẩu';
          } else {
            // hide
            pwdInput.type = 'password';
            icon.classList.remove('fa-eye');
            icon.classList.add('fa-eye-slash');
            toggleBtn.setAttribute('aria-pressed', 'false');
            toggleBtn.title = 'Hiển thị mật khẩu';
          }
        });
      }
    } catch (e) {
      console.error('Password toggle init error', e);
    }
  });

})();
