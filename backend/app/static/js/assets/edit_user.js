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
      const err = await res.json().catch(()=>({message:res.statusText}));
      throw new Error(err.message || 'Lỗi cập nhật');
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
      document.getElementById('editUserRole').value = user.role || 'user';
      document.getElementById('editUserStatus').value = (user.status === 'inactive' || user.isActive === false) ? 'inactive' : 'active';
      if (displayUserId) displayUserId.textContent = user.id || user._id || userId;

      // Summary panel
      if (summaryName) summaryName.textContent = nameVal || '—';
      if (summaryEmail) summaryEmail.textContent = user.email || '—';
      if (roleBadge) {
        roleBadge.textContent = (user.role || 'user').toUpperCase();
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
        const payload = {
          username: document.getElementById('editUserName').value.trim(),
          email: document.getElementById('editUserEmail').value.trim(),
          status: document.getElementById('editUserStatus').value
        };
        await saveUser(userId, payload);
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
