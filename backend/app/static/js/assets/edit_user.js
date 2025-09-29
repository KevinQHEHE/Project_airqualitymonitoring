// JS for admin edit user page
(function(window, document){
  async function loadUser(userId) {
    try {
      const token = localStorage.getItem('access_token') || '';
      const res = await fetch('/api/admin/users/' + userId, { headers: { 'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : '' }});
      if (!res.ok) {
        const body = await res.json().catch(()=>({message:res.statusText}));
        throw new Error(body.message || 'Không thể tải thông tin');
      }
      return await res.json();
    } catch (err) {
      throw err;
    }
  }

  async function saveUser(userId, payload) {
    const token = localStorage.getItem('access_token') || '';
    const res = await fetch('/api/admin/users/' + userId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : '' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      // parse body if possible and attach it + status to the thrown Error
      const body = await res.json().catch(()=>({ message: res.statusText }));
      const error = new Error(body && body.message ? body.message : res.statusText || 'Lỗi cập nhật');
      error.body = body;
      error.status = res.status;
      throw error;
    }
    return await res.json();
  }

  function decodeJwtRole(token) {
    try {
      if (!token) return null;
      const parts = token.split('.');
      if (parts.length !== 3) return null;
      const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      return payload && payload.role ? payload.role : null;
    } catch (e) {
      return null;
    }
  }

  // Initialize page when DOM is ready
  document.addEventListener('DOMContentLoaded', function(){
    try {
      const userIdEl = document.getElementById('editUserId');
      if (!userIdEl) throw new Error('Không tìm thấy element #editUserId');
      const userId = userIdEl.value;
      const displayUserId = document.getElementById('displayUserId');
      const saveStatus = document.getElementById('saveStatus');
      const saveBtn = document.getElementById('saveBtn');
      const formAlert = document.getElementById('formAlert');
      const userAvatar = document.getElementById('userAvatar');
      const summaryName = document.getElementById('summaryName');
      const summaryEmail = document.getElementById('summaryEmail');
      const createdAtEl = document.getElementById('createdAt');
      const updatedAtEl = document.getElementById('updatedAt');
      const roleBadge = document.getElementById('roleBadge');

    function showSaving(show) {
      try {
        if (saveStatus) saveStatus.style.display = show ? 'inline' : 'none';
      } catch (e) {
        // noop
      }
    }

    // Prevent role editing and set tooltip using JWT
    (function(){
      try {
        const roleField = document.getElementById('editUserRole');
        if (!roleField) return;
        roleField.setAttribute('readonly', 'readonly');
        roleField.classList.add('bg-light');
        const token = localStorage.getItem('access_token') || '';
        let reason = 'Vai trò không được chỉnh sửa từ giao diện này.';
        const r = decodeJwtRole(token);
        if (r) reason += ` Bạn đang đăng nhập với vai trò: ${r}.`;
        roleField.title = reason;
      } catch (e) {
        console.warn('Role field safety wrapper error:', e);
      }
    })();

    // Load and fill; populate summary
    loadUser(userId).then(user => {
      const nameVal = user.username || user.name || user.email || '';
      document.getElementById('editUserName').value = nameVal;
      document.getElementById('editUserEmail').value = user.email || '';
      // Show localized role labels in the UI (do not change underlying role value)
      const ROLE_LABELS = {
        user: 'Người dùng',
        admin: 'Quản trị viên'
      };
      const roleLabel = ROLE_LABELS[user.role] || (user.role || 'Người dùng');
      document.getElementById('editUserRole').value = roleLabel;
      document.getElementById('editUserStatus').value = (user.status === 'inactive' || user.isActive === false) ? 'inactive' : 'active';
      if (displayUserId) displayUserId.textContent = user.id || user._id || userId;

      // Summary panel
      if (summaryName) summaryName.textContent = nameVal || '—';
      if (summaryEmail) summaryEmail.textContent = user.email || '—';
      if (roleBadge) {
        roleBadge.textContent = ROLE_LABELS[user.role] || (user.role ? user.role.toString() : 'Người dùng');
        roleBadge.className = 'badge badge-role ' + (user.role === 'admin' ? 'bg-danger' : 'bg-secondary');
      }
      if (createdAtEl) createdAtEl.textContent = user.createdAt || '—';
      if (updatedAtEl) updatedAtEl.textContent = user.updatedAt || '—';

      // Avatar initials
      if (userAvatar) {
        const initials = (nameVal || '').split(' ').filter(Boolean).slice(0,2).map(s=>s[0].toUpperCase()).join('') || (user.email||'')[0]?.toUpperCase() || 'U';
        userAvatar.textContent = initials;
      }
    }).catch(err => {
      if (formAlert) {
        formAlert.style.display = 'block';
        formAlert.textContent = 'Lỗi tải thông tin người dùng: ' + err.message;
      } else {
        alert('Lỗi tải thông tin người dùng: ' + err.message);
      }
    });

    if (saveBtn) {
      saveBtn.addEventListener('click', async function(){
       try {
        // Clear previous field errors
        function clearFieldErrors() {
          try {
            const nF = document.getElementById('editUserNameFeedback');
            const eF = document.getElementById('editUserEmailFeedback');
            const nInput = document.getElementById('editUserName');
            const eInput = document.getElementById('editUserEmail');
            if (nF) { nF.style.display = 'none'; nF.textContent = ''; }
            if (eF) { eF.style.display = 'none'; eF.textContent = ''; }
            if (nInput) nInput.classList.remove('is-invalid');
            if (eInput) eInput.classList.remove('is-invalid');
          } catch (e) { /* noop */ }
        }

        function showFieldError(fieldId, message) {
          try {
            const fb = document.getElementById(fieldId + 'Feedback');
            const input = document.getElementById(fieldId);
            if (fb) {
              fb.textContent = message;
              fb.style.display = 'block';
            }
            if (input) input.classList.add('is-invalid');
          } catch (e) { /* noop */ }
        }

        function validateFormData(name, email) {
          const errors = {};
          if (!name || String(name).trim().length === 0) {
            errors.name = 'Tên hiển thị không được để trống.';
          } else if (String(name).trim().length < 3) {
            errors.name = 'Tên hiển thị phải ít nhất 3 ký tự.';
          }
          if (!email || String(email).trim().length === 0) {
            errors.email = 'Email không được để trống.';
          } else {
            const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!re.test(String(email).toLowerCase())) {
              errors.email = 'Email không đúng định dạng.';
            }
          }
          return errors;
        }
        const token = localStorage.getItem('access_token') || '';
        if (!token) {
          if (formAlert) {
            formAlert.classList.remove('alert-success');
            formAlert.classList.add('alert-danger');
            formAlert.style.display = 'block';
            formAlert.textContent = 'Không tìm thấy token xác thực. Vui lòng đăng nhập lại trước khi lưu.';
          } else {
            alert('Không tìm thấy token xác thực. Vui lòng đăng nhập lại.');
          }
          return;
        }
        showSaving(true);
        if (formAlert) { formAlert.style.display = 'none'; }
        clearFieldErrors();
        const nameVal = document.getElementById('editUserName').value.trim();
        const emailVal = document.getElementById('editUserEmail').value.trim();
        const clientErrors = validateFormData(nameVal, emailVal);
        if (clientErrors.name) showFieldError('editUserName', clientErrors.name);
        if (clientErrors.email) showFieldError('editUserEmail', clientErrors.email);
        if (Object.keys(clientErrors).length > 0) {
          showSaving(false);
          return;
        }

        const payload = {
          username: nameVal,
          email: emailVal,
          status: document.getElementById('editUserStatus').value
        };

        try {
          await saveUser(userId, payload);
        } catch (apiErr) {
          // Prefer structured body errors when available (set in saveUser)
          const body = apiErr && apiErr.body ? apiErr.body : null;
          const status = apiErr && apiErr.status ? apiErr.status : null;
          let handled = false;

          // If the API provided an errors object: map field keys to feedback
          if (body && typeof body === 'object') {
            // Example: { errors: { username: '...', email: '...' } }
            if (body.errors && typeof body.errors === 'object') {
              if (body.errors.username) { showFieldError('editUserName', body.errors.username); handled = true; }
              if (body.errors.name) { showFieldError('editUserName', body.errors.name); handled = true; }
              if (body.errors.email) { showFieldError('editUserEmail', body.errors.email); handled = true; }
            }

            // Mongo-like duplicate info: { keyValue: { username: 'trinh16' } }
            if (!handled && body.keyValue && typeof body.keyValue === 'object') {
              if (body.keyValue.username) { showFieldError('editUserName', 'Tên này đã tồn tại trong hệ thống.'); handled = true; }
              if (body.keyValue.email) { showFieldError('editUserEmail', 'Email này đã được sử dụng.'); handled = true; }
            }

            // Some APIs return { message: '...' } with hint text
            if (!handled && body.message && /E11000|duplicate|unique|409|Conflict/i.test(body.message)) {
              if (/username|user|login|name/i.test(body.message)) { showFieldError('editUserName', 'Tên này đã tồn tại trong hệ thống.'); handled = true; }
              if (/email/i.test(body.message)) { showFieldError('editUserEmail', 'Email này đã được sử dụng.'); handled = true; }
            }
          }

          // Fallbacks based on status or message when structured body wasn't helpful
          if (!handled) {
            const msg = apiErr && apiErr.message ? apiErr.message : String(apiErr);
            if (status === 409 || /E11000|duplicate|unique|409|Conflict/i.test(msg)) {
              // generic conflict - try both
              showFieldError('editUserName', 'Tên này đã tồn tại trong hệ thống.');
              showFieldError('editUserEmail', 'Email này đã được sử dụng.');
              handled = true;
            }
            if (!handled && /password|weak[_\- ]?password/i.test(msg)) {
              if (formAlert) {
                formAlert.classList.remove('alert-success');
                formAlert.classList.add('alert-danger');
                formAlert.style.display = 'block';
                formAlert.textContent = 'Mật khẩu còn yếu, vui lòng nhập lại mật khẩu.';
              }
              handled = true;
            }
            if (!handled) {
              if (formAlert) {
                formAlert.classList.remove('alert-success');
                formAlert.classList.add('alert-danger');
                formAlert.style.display = 'block';
                formAlert.textContent = 'Lỗi lưu: ' + msg;
              }
            }
          }
          showSaving(false);
          return;
        }
        // show a small success state then navigate
        if (formAlert) {
          formAlert.classList.remove('alert-danger');
          formAlert.classList.add('alert-success');
          formAlert.textContent = 'Cập nhật thành công';
          formAlert.style.display = 'block';
        } else {
          alert('Cập nhật thành công');
        }
        setTimeout(()=> window.location.href = '/admin', 700);
      } catch (err) {
        if (formAlert) {
          formAlert.classList.remove('alert-success');
          formAlert.classList.add('alert-danger');
          formAlert.style.display = 'block';
          formAlert.textContent = 'Lỗi lưu: ' + err.message;
        } else {
          alert('Lỗi lưu: ' + err.message);
        }
      } finally {
        showSaving(false);
      }
      });
    } else {
      console.warn('Save button (#saveBtn) not found - save disabled');
      if (formAlert) {
        formAlert.style.display = 'block';
        formAlert.classList.add('alert-warning');
        formAlert.textContent = 'Lưu tạm thời bị vô hiệu (không tìm thấy nút Lưu).';
      }
    }
  } catch (initErr) {
    console.error('Initialization error in edit_user.js:', initErr);
    const formAlert = document.getElementById('formAlert');
    if (formAlert) {
      formAlert.style.display = 'block';
      formAlert.classList.remove('alert-success');
      formAlert.classList.add('alert-danger');
      formAlert.textContent = 'Lỗi khởi tạo trang: ' + (initErr && initErr.message ? initErr.message : String(initErr));
    } else {
      alert('Lỗi khởi tạo trang: ' + (initErr && initErr.message ? initErr.message : String(initErr)));
    }
  }
  });
})(window, document);
