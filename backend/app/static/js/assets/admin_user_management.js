/**
 * Admin User Management Dashboard
 * Handles search, filtering, pagination, bulk actions, and CSV export
 */

class AdminUserManagement {
    constructor() {
        this.currentPage = 1;
        this.itemsPerPage = 25;
        this.totalUsers = 0;
        this.searchTimeout = null;
        this.selectedUsers = new Set();
        this.mockUsers = this.generateMockData(); // Sample data for frontend testing
        
        this.initializeEventListeners();
        this.loadUsers();
    }

    generateMockData() {
        // Sample user data for testing frontend
        return [
            {
                _id: '507f1f77bcf86cd799439011',
                username: 'admin',
                email: 'admin@example.com',
                fullname: 'Administrator',
                role: 'admin',
                isActive: true,
                emailVerified: true,
                createdAt: '2024-01-15T08:30:00Z',
                favoriteLocations: ['Ho Chi Minh City', 'Hanoi'],
                alertSettings: {
                    enableEmail: true,
                    enablePush: true,
                    thresholds: { pm25: 50, pm10: 80 }
                }
            },
            {
                _id: '507f1f77bcf86cd799439012',
                username: 'johnsmith',
                email: 'john.smith@gmail.com',
                fullname: 'John Smith',
                role: 'user',
                isActive: true,
                emailVerified: true,
                createdAt: '2024-02-10T14:22:00Z',
                favoriteLocations: ['Da Nang', 'Nha Trang'],
                alertSettings: {
                    enableEmail: true,
                    enablePush: false,
                    thresholds: { pm25: 35, pm10: 50 }
                }
            },
            {
                _id: '507f1f77bcf86cd799439013',
                username: 'maryjane',
                email: 'mary.jane@yahoo.com',
                fullname: 'Mary Jane',
                role: 'user',
                isActive: false,
                emailVerified: false,
                createdAt: '2024-03-05T10:15:00Z',
                favoriteLocations: ['Can Tho'],
                alertSettings: {
                    enableEmail: false,
                    enablePush: true,
                    thresholds: { pm25: 25, pm10: 40 }
                }
            },
            {
                _id: '507f1f77bcf86cd799439014',
                username: 'nguyenvan',
                email: 'nguyen.van@outlook.com',
                fullname: 'Nguyen Van A',
                role: 'user',
                isActive: true,
                emailVerified: true,
                createdAt: '2024-01-20T16:45:00Z',
                favoriteLocations: ['Ho Chi Minh City', 'Vung Tau', 'Long An'],
                alertSettings: {
                    enableEmail: true,
                    enablePush: true,
                    thresholds: { pm25: 40, pm10: 70 }
                }
            },
            {
                _id: '507f1f77bcf86cd799439015',
                username: 'sarahconnor',
                email: 'sarah.connor@hotmail.com',
                fullname: 'Sarah Connor',
                role: 'user',
                isActive: true,
                emailVerified: true,
                createdAt: '2024-02-28T09:30:00Z',
                favoriteLocations: ['Hanoi', 'Hai Phong'],
                alertSettings: {
                    enableEmail: false,
                    enablePush: false,
                    thresholds: { pm25: 60, pm10: 90 }
                }
            }
        ];
    }

    initializeEventListeners() {
        // Search functionality with debounce
        const searchInput = document.getElementById('userSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.handleSearch(e.target.value);
                }, 300);
            });
        }

        // Search button (new id added in template)
        const searchBtn = document.getElementById('searchBtn');
        if (searchBtn) {
            searchBtn.addEventListener('click', () => {
                const q = document.getElementById('userSearch')?.value || '';
                this.handleSearch(q);
            });
        }

        // Filter by date range
        const dateFrom = document.getElementById('dateFrom');
        const dateTo = document.getElementById('dateTo');
        if (dateFrom && dateTo) {
            dateFrom.addEventListener('change', () => this.handleDateFilter());
            dateTo.addEventListener('change', () => this.handleDateFilter());
        }

        // Status filter
        const statusFilter = document.getElementById('statusFilter');
        if (statusFilter) {
            statusFilter.addEventListener('change', () => this.handleStatusFilter());
        }

        // Bulk action buttons (only export is wired here)
        const bulkExportBtn = document.getElementById('bulkExport');
        if (bulkExportBtn) {
            bulkExportBtn.addEventListener('click', () => this.exportToCSV());
        }

        // Select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllUsers');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                this.handleSelectAll(e.target.checked);
            });
        }

        // Individual user checkboxes (delegated event)
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('user-checkbox')) {
                this.handleUserSelect(e.target.value, e.target.checked);
            }
        });

        // User detail modal triggers - use closest to handle clicks on inner elements
        document.addEventListener('click', (e) => {
            const btn = e.target.closest && e.target.closest('.view-user-btn');
            if (btn) {
                const userId = btn.dataset.userId;
                this.showUserDetail(userId);
            }
        });

        // Inline status toggle
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('status-toggle')) {
                const userId = e.target.dataset.userId;
                const isActive = e.target.checked;
                this.toggleUserStatus(userId, isActive);
            }
        });

        // Role change
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('role-select')) {
                const userId = e.target.dataset.userId;
                const newRole = e.target.value;
                this.changeUserRole(userId, newRole);
            }
        });

        // Pagination
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('page-link')) {
                e.preventDefault();
                const page = parseInt(e.target.dataset.page);
                if (page && page !== this.currentPage) {
                    this.currentPage = page;
                    this.loadUsers();
                }
            }
        });

        // (edit action moved to table actions as compact icon/link)
    }

    async loadUsers() {
        try {
            this.showLoading(true);
            
            // Check if we have an auth token
            const token = this.getAuthToken();
            if (!token) {
                throw new Error('Không tìm thấy token xác thực. Vui lòng đăng nhập lại.');
            }
            
            // Build query parameters for API call
            const searchTerm = document.getElementById('userSearch')?.value || '';
            const statusFilter = document.getElementById('statusFilter')?.value || '';
            const dateFrom = document.getElementById('dateFrom')?.value || '';
            const dateTo = document.getElementById('dateTo')?.value || '';
            
            const params = new URLSearchParams({
                page: this.currentPage.toString(),
                page_size: this.itemsPerPage.toString(),
                sort: 'created_at',
                order: 'desc'
            });
            
            if (searchTerm) {
                params.append('search', searchTerm);
            }
            
            if (statusFilter === 'active') {
                params.append('status', 'active');
            } else if (statusFilter === 'inactive') {
                params.append('status', 'inactive');
            }
            
            if (dateFrom) {
                params.append('registered_after', dateFrom + 'T00:00:00Z');
            }
            if (dateTo) {
                params.append('registered_before', dateTo + 'T23:59:59Z');
            }
            // Only load regular users in the admin list (exclude admin accounts)
            // Prefer telling the API to filter server-side, and also defensively
            // filter client-side in case the API doesn't support the param.
            params.append('role', 'user');
            
            // Call real API
            const response = await fetch(`/api/admin/users/?${params}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (response.status === 401) {
                throw new Error('Token xác thực không hợp lệ. Vui lòng đăng nhập lại.');
            }
            
            if (response.status === 403) {
                throw new Error('Bạn không có quyền truy cập chức năng này. Cần quyền admin.');
            }
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            // Prefer server-side filtered results; defensively filter client-side
            const apiUsers = Array.isArray(result.users) ? result.users : [];
            const users = apiUsers.filter(u => ((u.role || '') + '').toLowerCase() === 'user');
            this.totalUsers = users.length;
            this.renderUserTable(users);
            this.renderPagination(users.length, Math.ceil(users.length / this.itemsPerPage));
            this.updateBulkActionButtons();
            
        } catch (error) {
            console.error('Error loading users:', error);
            this.showError('Lỗi tải dữ liệu người dùng: ' + error.message);
            
            // Fallback to mock data in case of API error
            this.loadMockData();
        } finally {
            this.showLoading(false);
        }
    }

    loadMockData() {
        // Fallback method using mock data when API fails
        // Only include mock entries that represent regular users
        const filteredUsers = (this.mockUsers || []).filter(u => ((u.role || '') + '').toLowerCase() === 'user');
        this.totalUsers = filteredUsers.length;
        this.renderUserTable(filteredUsers);
        this.renderPagination(filteredUsers.length, Math.ceil(filteredUsers.length / this.itemsPerPage));
        this.updateBulkActionButtons();
    }

    renderUserTable(users) {
        // Defensive: ensure admins are excluded even if upstream passed them
        users = (users || []).filter(u => ((u.role || '') + '').toLowerCase() === 'user');
    const tbody = document.getElementById('userTableBody') || document.querySelector('#userTable tbody');
        if (!tbody) return;

        tbody.innerHTML = users.map(user => `
            <tr>
                <td>
                    <div class="form-check">
                        <input class="form-check-input user-checkbox" type="checkbox" 
                               value="${user._id || user.id}" ${this.selectedUsers.has(user._id || user.id) ? 'checked' : ''}>
                    </div>
                </td>
                <td>
                    ${this.renderUserHeading(user)}
                </td>
                <td>
                    <select class="form-select form-select-sm role-select" data-user-id="${user._id || user.id}">
                        <option value="user" ${user.role === 'user' ? 'selected' : ''}>User</option>
                    </select>
                </td>
                <td>
                    <div class="form-check form-switch">
                        <input class="form-check-input status-toggle" type="checkbox" 
                               data-user-id="${user._id || user.id}" ${(user.isActive !== false && user.status !== 'inactive') ? 'checked' : ''}>
                        <label class="form-check-label">
                            ${(user.isActive !== false && user.status !== 'inactive') ? 'Hoạt động' : 'Không hoạt động'}
                        </label>
                    </div>
                </td>
                <td>
                    <div class="d-flex flex-column">
                        <small class="text-muted">Tham gia: ${new Date(user.createdAt || user.created_at).toLocaleDateString('vi-VN')}</small>
                    </div>
                </td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-primary view-user-btn" data-user-id="${user._id || user.id}" title="Chi tiết">
                            <i class="fas fa-eye"></i>
                        </button>
                        <a class="btn btn-sm btn-outline-secondary" href="/admin/users/${user._id || user.id}/edit" title="Chỉnh sửa">
                            <i class="fas fa-edit"></i>
                        </a>
                    </div>
                </td>
            </tr>
        `).join('');
    }

    // Helper to render the heading for a user row. Prefer fullname, then username if it's not the same as email.
    
    
    renderUserHeading(user) {
        // This method returns an HTML string for the name/heading element
        const fullname = (user.fullname || user.name || '').trim();
        const username = (user.username || user.name || '').trim();
        const email = (user.email || '').trim();

        // If fullname exists and is not the email, show it; otherwise prefer username when it's not equal to email
        let headingText = '';
        if (fullname && fullname !== email) {
            headingText = fullname;
        } else if (username && username !== email) {
            headingText = username;
        } else if (email) {
            // Last resort: show email as heading (but email will also be the small text below) — avoid duplication handled by template
            headingText = email;
        } else {
            headingText = '';
        }

        return `<h6 class="mb-0">${headingText}</h6>`;
    }

    // Helper to get a readable location/station name from various data shapes
    getLocationName(loc, idx) {
        if (!loc) return `Trạm ${idx+1}`;
        if (typeof loc === 'string' && loc.trim() !== '') return loc.trim();

        // Helper to decide whether a found name is meaningful (not a generic code)
        const isMeaningful = (s) => {
            if (!s || typeof s !== 'string') return false;
            const t = s.trim();
            if (t.length < 3) return false;
            // Generic codes like "TRAM 1583", "TRẠM 1583" are common — prefer richer names
            if (/^\s*(TRAM|TRẠM)\s*\d+\s*$/i.test(t)) return false;
            return true;
        };

    // First, prefer direct subscription-level or display fields if they are meaningful
    const preferredFields = ['canonical_display_name','station_name', 'display_name', 'displayName', 'name', 'label', 'title', 'nickname'];
        for (const f of preferredFields) {
            const v = (loc[f] ?? (loc._raw && loc._raw[f]) ?? (loc.metadata && loc.metadata[f]) ?? (loc._station && loc._station[f]));
            if (isMeaningful(v)) return v.trim();
        }

        // Search nested paths that often contain a human-friendly name
        const nestedPaths = [
            ['_station','display_name'], ['_station','name'], ['_station','title'],
            ['_raw','station','name'], ['_raw','station','display_name'], ['_raw','name'],
            ['metadata','nickname'], ['meta','name'], ['properties','name'], ['info','name'], ['attributes','name'], ['station','name']
        ];
        for (const path of nestedPaths) {
            let cur = loc;
            for (const key of path) {
                if (cur && typeof cur === 'object' && key in cur) cur = cur[key]; else { cur = null; break; }
            }
            if (isMeaningful(cur)) return cur.trim();
        }

        // Language-specific name object, e.g., { name: { vi: '...', en: '...' } }
        if (loc.name && typeof loc.name === 'object') {
            for (const k of ['vi','en','local','default']) {
                if (isMeaningful(loc.name[k])) return loc.name[k].trim();
            }
        }

        // If station_name exists but was generic (e.g., TRAM 1583), return it as a last-ditch
        // option after trying richer fields, so the UI at least shows something stable.
        if (loc.station_name && typeof loc.station_name === 'string' && loc.station_name.trim() !== '') return loc.station_name.trim();

        // fallback: if coordinates exist, show lat,lng
        if (Array.isArray(loc.coordinates) && loc.coordinates.length >= 2) return `${loc.coordinates[1]}, ${loc.coordinates[0]}`;

        // last resort: use generic index label
        return `Trạm ${idx+1}`;
    }

    // Simple HTML escaper to avoid injecting untrusted HTML into innerHTML
    escapeHtml(str) {
        if (str === null || typeof str === 'undefined') return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    getHeadingText(user) {
        const fullname = (user.fullname || user.name || '').trim();
        const username = (user.username || user.name || '').trim();
        const email = (user.email || '').trim();
        if (fullname && fullname !== '') return fullname;
        if (username && username !== '') return username;
        return email || '';
    }

    renderPagination(total, totalPages) {
        const paginationContainer = document.getElementById('paginationContainer');
        if (!paginationContainer) return;

        const startItem = (this.currentPage - 1) * this.itemsPerPage + 1;
        const endItem = Math.min(this.currentPage * this.itemsPerPage, total);

        // Update showing info
        const showingInfo = document.getElementById('showingInfo');
        if (showingInfo) {
            showingInfo.textContent = `Hiển thị ${startItem} - ${endItem} trong tổng số ${total} người dùng`;
        }

        // Generate pagination buttons
        let paginationHTML = `
            <nav>
                <ul class="pagination justify-content-center">
                    <li class="page-item ${this.currentPage === 1 ? 'disabled' : ''}">
                        <a class="page-link" href="#" data-page="${this.currentPage - 1}">Trước</a>
                    </li>
        `;

        // Show page numbers (max 5 pages visible)
        const maxVisible = 5;
        let startPage = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
        let endPage = Math.min(totalPages, startPage + maxVisible - 1);
        
        if (endPage - startPage + 1 < maxVisible) {
            startPage = Math.max(1, endPage - maxVisible + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            paginationHTML += `
                <li class="page-item ${i === this.currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }

        paginationHTML += `
                    <li class="page-item ${this.currentPage === totalPages ? 'disabled' : ''}">
                        <a class="page-link" href="#" data-page="${this.currentPage + 1}">Sau</a>
                    </li>
                </ul>
            </nav>
        `;

        paginationContainer.innerHTML = paginationHTML;
    }

    handleSearch(query) {
        this.currentPage = 1;
        this.loadUsers();
    }

    handleDateFilter() {
        this.currentPage = 1;
        this.loadUsers();
    }

    handleStatusFilter() {
        this.currentPage = 1;
        this.loadUsers();
    }

    handleSelectAll(checked) {
        const checkboxes = document.querySelectorAll('.user-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.checked = checked;
            if (checked) {
                this.selectedUsers.add(checkbox.value);
            } else {
                this.selectedUsers.delete(checkbox.value);
            }
        });
        this.updateBulkActionButtons();
    }

    handleUserSelect(userId, checked) {
        if (checked) {
            this.selectedUsers.add(userId);
        } else {
            this.selectedUsers.delete(userId);
        }
        
        // Update select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllUsers');
        const allCheckboxes = document.querySelectorAll('.user-checkbox');
        const checkedCheckboxes = document.querySelectorAll('.user-checkbox:checked');
        
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = checkedCheckboxes.length === allCheckboxes.length;
            selectAllCheckbox.indeterminate = checkedCheckboxes.length > 0 && checkedCheckboxes.length < allCheckboxes.length;
        }

        this.updateBulkActionButtons();
    }

    updateBulkActionButtons() {
        const hasSelected = this.selectedUsers.size > 0;
        const bulkButtons = document.querySelectorAll('.bulk-action-btn');
        const bulkActions = document.getElementById('bulkActions');
        
        bulkButtons.forEach(btn => {
            btn.disabled = !hasSelected;
        });

        // Show/hide bulk actions toolbar
        if (bulkActions) {
            if (hasSelected) {
                bulkActions.classList.add('show');
            } else {
                bulkActions.classList.remove('show');
            }
        }

        // Update selected count
        const selectedCount = document.getElementById('selectedCount');
        if (selectedCount) {
            selectedCount.textContent = this.selectedUsers.size;
        }
    }

    async handleBulkAction(action) {
        if (this.selectedUsers.size === 0) return;

        const actionText = action === 'activate' ? 'kích hoạt' : 'vô hiệu hóa';
        const confirmed = await this.showConfirmDialog(
            `Xác nhận ${actionText}`,
            `Bạn có chắc chắn muốn ${actionText} ${this.selectedUsers.size} người dùng đã chọn?`
        );

        if (!confirmed) return;

        try {
            this.showLoading(true);

            // Update mock data instead of API call
            const isActive = action === 'activate';
            let affectedCount = 0;
            
            this.selectedUsers.forEach(userId => {
                const user = this.mockUsers.find(u => u._id === userId);
                if (user && user.isActive !== isActive) {
                    user.isActive = isActive;
                    affectedCount++;
                }
            });

            this.showSuccess(`Đã ${actionText} ${affectedCount} người dùng`);
            this.selectedUsers.clear();
            this.loadUsers();
            
        } catch (error) {
            console.error('Bulk action error:', error);
            this.showError('Lỗi thực hiện thao tác hàng loạt');
        } finally {
            this.showLoading(false);
        }
    }

    async toggleUserStatus(userId, isActive) {
        try {
            // Call real API to update user status
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({
                    status: isActive ? 'active' : 'inactive'
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            this.showSuccess(`Đã ${isActive ? 'kích hoạt' : 'vô hiệu hóa'} người dùng thành công`);
            
            // Update the label text
            const checkbox = document.querySelector(`.status-toggle[data-user-id="${userId}"]`);
            if (checkbox) {
                const label = checkbox.nextElementSibling;
                if (label) {
                    label.textContent = isActive ? 'Hoạt động' : 'Không hoạt động';
                }
            }
            
        } catch (error) {
            console.error('Error toggling user status:', error);
            this.showError(`Lỗi cập nhật trạng thái: ${error.message}`);
            
            // Revert the checkbox state on error
            const checkbox = document.querySelector(`[data-user-id="${userId}"].status-toggle`);
            if (checkbox) {
                checkbox.checked = !isActive;
            }
        }
    }

    // Bulk change status: toggle selected users between active/inactive (asks for target state)
    async bulkChangeStatus() {
        if (this.selectedUsers.size === 0) return;

        const confirmed = await this.showConfirmDialog(
            'Chuyển trạng thái',
            `Bạn có chắc chắn muốn chuyển trạng thái ${this.selectedUsers.size} người dùng đã chọn?`
        );

        if (!confirmed) return;

        // Ask which state to set
        const setActive = confirm('Nhấn OK để đặt là Hoạt động, Cancel để đặt là Không hoạt động.');

        try {
            this.showLoading(true);
            let affected = 0;
            this.selectedUsers.forEach(userId => {
                const user = this.mockUsers.find(u => u._id === userId);
                if (user) {
                    user.isActive = setActive;
                    affected++;
                }
            });

            this.showSuccess(`Đã cập nhật trạng thái cho ${affected} người dùng`);
            this.selectedUsers.clear();
            this.loadUsers();
        } catch (err) {
            console.error(err);
            this.showError('Lỗi khi chuyển trạng thái');
        } finally {
            this.showLoading(false);
        }
    }

    async changeUserRole(userId, newRole) {
        try {
            // Call real API to update user role
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({
                    role: newRole
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            this.showSuccess(`Đã thay đổi vai trò thành ${newRole}`);
            
        } catch (error) {
            console.error('Error changing user role:', error);
            this.showError(`Lỗi thay đổi vai trò: ${error.message}`);
            
            // Revert select value on error
            const select = document.querySelector(`.role-select[data-user-id="${userId}"]`);
            if (select) {
                // Try to get previous value from the currently selected user data
                const user = this.mockUsers.find(u => (u._id || u.id) === userId);
                select.value = user ? user.role : 'user';
            }
        }
    }

    async showUserDetail(userId) {
        try {
            this.showLoading(true);
            // If no token, avoid calling protected API — fallback to mock and prompt login
            const token = this.getAuthToken();
            if (!token) {
                this.showToast('Bạn chưa đăng nhập. Hiển thị dữ liệu mẫu.', 'info');
                const user = this.mockUsers.find(u => u._id === userId || u.id === userId);
                if (user) {
                    this.renderUserDetailModal(user);
                    const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
                    modal.show();
                    return;
                }
                // if no mock found, show friendly error
                this.showError('Không tìm thấy thông tin người dùng (đã thử dữ liệu mẫu)');
                return;
            }

            // Call real API to get user details
            const response = await fetch(`/api/admin/users/${userId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.status === 401) {
                // Token invalid — ask user to login
                this.showError('Phiên đã hết hạn hoặc không hợp lệ. Vui lòng đăng nhập lại.');
                throw new Error('Unauthorized');
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const user = await response.json();
            // Try to fetch detailed locations/subscriptions for this user from admin API
            try {
                const locRes = await fetch(`/api/admin/users/${userId}/locations`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    }
                });
                if (locRes.ok) {
                    const locJson = await locRes.json();
                    console.log('=== DEBUG: Raw locations API response ===');
                    console.log('Full locJson:', locJson);
                    console.log('locJson keys:', Object.keys(locJson || {}));
                    console.log('=== END DEBUG ===');
                    // Merge locations and alert settings into user object if provided
                    if (locJson && typeof locJson === 'object') {
                        // Normalize various possible shapes into a consistent `favoriteLocations` array
                        let rawSubs = locJson.favorite_locations || locJson.favoriteLocations || locJson.locations || locJson.subscriptions || [];
                        // If API returned an object map (e.g. { "1583": { ... } }) convert to array
                        if (rawSubs && !Array.isArray(rawSubs) && typeof rawSubs === 'object') {
                            rawSubs = Object.keys(rawSubs).map(k => {
                                const v = rawSubs[k];
                                // If value is a primitive, wrap it
                                if (v === null || typeof v !== 'object') return { station_id: k, value: v };
                                // Merge station id into the object for easier normalization
                                return Object.assign({ station_id: k }, v);
                            });
                        }
                        // Normalizer: produce objects with consistent keys used by the UI
                        const normalizeSubscription = (s, idx) => {
                            if (!s) return null;
                            // Common shapes handled:
                            // - { station_id, station_name, created_at, current_aqi, threshold, alert_enabled }
                            // - { station: { name, id }, created_at, latest_reading: { aqi } }
                            // - strings (station id) or simple ids
                            const out = {};
                            // Try to get station id
                            out.station_id = s.station_id || s.id || s._id || s.station?.id || s.station_idx || s.station?.station_id || null;
                            // Carry subscription identifiers for later lookups so we can match updates
                            out.id = s.id || s._id || s.subscription_id || s.subscriptionId || s.alert_subscription_id || null;
                            out.subscription_id = s.subscription_id || s.subscriptionId || s.alert_subscription_id || null;
                            if (!out.id && out.subscription_id) {
                                out.id = out.subscription_id;
                            }
                            // Station name variants - prefer friendly nickname/name/display_name and avoid generic 'Trạm ####'
                            const _pickFriendly = (obj) => {
                                if (!obj) return null;
                                const cand = [obj.canonical_display_name, obj.display_name, obj.nickname, obj.station_name, obj.name, obj.title, obj.label, obj.location, (obj._raw && obj._raw.station_name), (obj._raw && obj._raw.name)];
                                const genericRe = /^\s*(TRAM|TRẠM)\s*\d+\s*$/i;
                                for (const c of cand) {
                                    if (!c || typeof c !== 'string') continue;
                                    const t = c.trim();
                                    if (!t) continue;
                                    if (genericRe.test(t)) continue;
                                    return t;
                                }
                                // fallback to the first available non-empty string if all are generic
                                for (const c of cand) {
                                    if (c && typeof c === 'string' && c.trim()) return c.trim();
                                }
                                return null;
                            };
                            out.station_name = _pickFriendly(s) || null;
                            // Timestamps (accept camelCase createdAt too)
                            out.created_at = s.created_at || s.added_at || s.createdAt || s.ts || null;
                            // AQI/latest reading - try many possible variations (explicit null/undefined checks)
                            out.current_aqi = (typeof s.current_aqi !== 'undefined' && s.current_aqi !== null) ? s.current_aqi
                                : (typeof s.aqi !== 'undefined' && s.aqi !== null) ? s.aqi
                                : (s.latest_reading?.aqi ?? s.latest?.aqi ?? (s.latest_reading && s.latest_reading.aqi) ?? s.reading?.aqi ?? s.lastReading?.aqi ?? s.currentReading?.aqi ?? s.data?.aqi ?? s.measurements?.aqi ?? s.value?.aqi ?? s.airQuality?.aqi ?? s.pm25 ?? s.PM25 ?? null);
                            // Threshold / user preference - try various field names (preserve 0)
                            out.threshold = (typeof s.threshold !== 'undefined' && s.threshold !== null) ? s.threshold
                                : (typeof s.alert_threshold !== 'undefined' && s.alert_threshold !== null) ? s.alert_threshold
                                : (typeof s.user_threshold !== 'undefined' && s.user_threshold !== null) ? s.user_threshold
                                : (s.settings?.threshold ?? s.alertThreshold ?? s.userThreshold ?? s.notification_threshold ?? s.notificationThreshold ?? s.preferences?.threshold ?? null);
                            // Alert enabled flag
                            out.alert_enabled = (typeof s.alert_enabled !== 'undefined') ? s.alert_enabled : (typeof s.enabled !== 'undefined' ? s.enabled : (typeof s.status !== 'undefined' ? s.status === 'active' : (s.notifications?.enabled ?? false)));
                            if (typeof s.status !== 'undefined') {
                                out.status = s.status;
                            }
                            // Attach raw object for debugging/edge cases
                            out._raw = s;
                            // If name is missing, fall back to generated label
                            if (!out.station_name) out.station_name = `Trạm ${idx + 1}`;
                            return out;
                        };

                        const normalized = Array.isArray(rawSubs) ? rawSubs.map((s, i) => normalizeSubscription(s, i)).filter(Boolean) : [];
                        user.favoriteLocations = normalized;
                        if (Array.isArray(locJson.subscriptions)) {
                            user.subscriptions = locJson.subscriptions;
                        } else if (!Array.isArray(user.subscriptions)) {
                            user.subscriptions = normalized;
                        }

                        // Enrich subscriptions that lack human-readable name or AQI by fetching station details
                        try {
                            const toEnrich = user.favoriteLocations.filter(s => (!s.station_name || typeof s.current_aqi === 'undefined' || s.current_aqi === null) && s.station_id).map(s => s.station_id);
                            if (toEnrich.length > 0) {
                                // Use Promise.all to fetch station details in parallel
                                const enrichPromises = toEnrich.map(async (sid) => {
                                    // Try the canonical station endpoint first, then fallbacks when 404
                                    const tryFetch = async (idToTry) => {
                                        try {
                                            const res = await fetch(`/api/stations/${encodeURIComponent(idToTry)}`, {
                                                method: 'GET',
                                                headers: {
                                                    'Content-Type': 'application/json',
                                                    'Authorization': `Bearer ${token}`
                                                }
                                            });
                                            if (res.ok) return await res.json();
                                            return null;
                                        } catch (e) {
                                            return null;
                                        }
                                    };

                                    // Primary attempt
                                    let staJson = await tryFetch(sid);
                                    if (!staJson) {
                                        // If sid contains a colon (e.g. '13665:1'), try the part before the colon
                                        if (typeof sid === 'string' && sid.includes(':')) {
                                            const [first] = sid.split(':');
                                            staJson = await tryFetch(first);
                                        }
                                    }
                                    if (!staJson) {
                                        // Try numeric cast of sid
                                        try {
                                            const numeric = parseInt(sid, 10);
                                            if (!isNaN(numeric)) {
                                                staJson = await tryFetch(String(numeric));
                                            }
                                        } catch (e) {
                                            // ignore
                                        }
                                    }

                                    if (!staJson) return null;
                                    // Some station endpoints return { station: { ... } }
                                    const payload = (staJson && staJson.station) ? staJson.station : staJson;
                                    return { id: sid, data: payload };
                                });

                                const enrichResults = await Promise.all(enrichPromises);
                                enrichResults.forEach(res => {
                                    if (!res) return;
                                    const sid = res.id;
                                    const data = res.data;
                                    const target = user.favoriteLocations.find(x => String(x.station_id) === String(sid));
                                    if (!target) return;
                                    // Pick sensible name fields from station object
                                    target.station_name = target.station_name || data.name || data.title || data.displayName || data.meta?.name || data.properties?.name || data.location || null;
                                    // Try to pick latest reading aqi - expanded search and coerce to number when possible
                                    const foundAqi = target.current_aqi || data.latest_reading?.aqi || data.latest?.aqi || 
                                                        data.reading?.aqi || data.lastReading?.aqi || data.currentReading?.aqi ||
                                                        data.airQuality?.aqi || data.measurements?.aqi || data.data?.aqi ||
                                                        data.pm25 || data.PM25 || data.aqi || null;
                                    target.current_aqi = (foundAqi === null || typeof foundAqi === 'undefined') ? null : (isNaN(Number(foundAqi)) ? foundAqi : Number(foundAqi));
                                    // Attach station raw for debugging
                                    target._station = data;
                                });
                            }
                        } catch (err) {
                            console.warn('Failed to enrich subscription station details:', err);
                        }

                        // Merge alert settings
                        if (locJson.alert_settings || locJson.alertSettings) {
                            user.alertSettings = locJson.alert_settings || locJson.alertSettings;
                        }
                    }
                }
            } catch (e) {
                console.warn('Could not load user locations (admin API):', e);
            }

            this.renderUserDetailModal(user);
            const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
            modal.show();
            
        } catch (error) {
            console.error('Error loading user details:', error);
            
            // Fallback to mock data
            const user = this.mockUsers.find(u => u._id === userId || u.id === userId);
            if (user) {
                this.renderUserDetailModal(user);
                const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
                modal.show();
            } else {
                this.showError('Không tìm thấy thông tin người dùng');
            }
        } finally {
            this.showLoading(false);
        }
    }

    renderUserDetailModal(user) {
                // Map user fields safely
                const fullname = user.fullname || user.name || user.username || '';
                const email = user.email || '';
                const id = user._id || user.id || '';
                const isActive = (typeof user.isActive !== 'undefined') ? user.isActive : (user.status !== 'inactive');
                const role = user.role || 'user';
                const createdAt = user.createdAt || user.created_at || '';
                const lastLogin = user.last_login || user.lastLogin || '';

                // Attach user id and data to modal for later use
                const modal = document.getElementById('userDetailModal');
                if (modal) {
                    modal.dataset.userId = id;
                    // Store the full user data for access in renderUserAlerts
                    modal.userData = user;
                }

                // Update modal title
                const titleEl = document.getElementById('userDetailModalLabel');
                if (titleEl) titleEl.innerHTML = `<i class="fas fa-user me-2"></i>Chi tiết: ${fullname}`;

        // Basic info content - minimal fields as requested
        const basicInfo = document.getElementById('basicInfoContent');
        if (basicInfo) {
            const statusText = isActive ? 'Hoạt động' : 'Không hoạt động';
            const roleText = role === 'admin' ? 'Quản trị viên' : 'Người dùng';
            basicInfo.innerHTML = `
                <div class="row g-3">
                    <div class="col-12"><div class="user-info-row"><div class="user-info-label fw-bold">ID:</div><div class="user-info-value">#${id}</div></div></div>
                    <div class="col-12"><div class="user-info-row"><div class="user-info-label fw-bold">Email:</div><div class="user-info-value">${email}</div></div></div>
                    <div class="col-12"><div class="user-info-row"><div class="user-info-label fw-bold">Vai trò:</div><div class="user-info-value">${roleText}</div></div></div>
                    <div class="col-12"><div class="user-info-row"><div class="user-info-label fw-bold">Trạng thái:</div><div class="user-info-value">${statusText}</div></div></div>
                    <div class="col-12"><div class="user-info-row"><div class="user-info-label fw-bold">Ngày tham gia:</div><div class="user-info-value">${createdAt ? new Date(createdAt).toLocaleDateString('vi-VN') : ''}</div></div></div>
                </div>
            `;
        }

                // Locations tab
                const locationsContent = document.getElementById('locationsContent');
                if (locationsContent) {
                        const locations = user.favoriteLocations || user.favorite_locations || [];
                        if (!locations || locations.length === 0) {
                                locationsContent.innerHTML = `
                                        <div class="text-center py-4">
                                                <i class="fas fa-map-marker-alt fa-3x text-muted mb-3"></i>
                                                <p class="text-white-50">Người dùng chưa có địa điểm yêu thích nào</p>
                                        </div>
                                `;
                        } else {
                                let html = '<div class="row g-3">';
                // helper to pick friendly display name for rendering
                const pickFriendlyFrom = (obj, idx) => {
                    if (!obj) return this.getLocationName(obj, idx);
                    const candidates = [obj.nickname, obj.name, obj.display_name, obj.canonical_display_name, obj.station_name, obj.label, obj.title];
                    const genericRe = /^\s*(TRAM|TRẠM)\s*\d+\s*$/i;
                    for (const c of candidates) {
                        if (!c || typeof c !== 'string') continue;
                        const t = c.trim();
                        if (!t) continue;
                        if (genericRe.test(t)) continue;
                        return t;
                    }
                    // fallback to existing robust getter
                    return this.getLocationName(obj, idx);
                };

                locations.forEach((loc, idx) => {
                    const name = pickFriendlyFrom(loc, idx);
                    const coords = Array.isArray(loc.coordinates) ? `${loc.coordinates[0]}, ${loc.coordinates[1]}` : (loc.coordinates || '');
                    const alertsEnabled = (typeof loc.alerts_enabled !== 'undefined') ? loc.alerts_enabled : (typeof loc.alertsEnabled !== 'undefined' ? loc.alertsEnabled : (typeof loc.status !== 'undefined' ? loc.status === 'active' : false));
                                        html += `
                                                <div class="col-md-6">
                                                    <div class="admin-card p-3">
                                                        <div class="d-flex justify-content-between align-items-start">
                                                            <div>
                                                                <h6 class="text-white mb-1"><i class="fas fa-map-marker-alt text-primary me-2"></i>${name}</h6>
                                                                <p class="text-white-50 small mb-0">${coords}</p>
                                                            </div>
                                                            <span class="badge ${alertsEnabled ? 'bg-success' : 'bg-secondary'}">${alertsEnabled ? 'Bật cảnh báo' : 'Tắt cảnh báo'}</span>
                                                        </div>
                                                    </div>
                                                </div>
                                        `;
                                });
                                html += '</div>';
                                locationsContent.innerHTML = html;
                        }
                }

                // Alerts tab
                const alertsContent = document.getElementById('alertsContent');
                if (alertsContent) {
                        const alertSettings = user.alertSettings || user.alert_settings || {};
                        // Prefer explicit `subscriptions` returned by admin API; fall back to favoriteLocations
                        const rawSubscriptions = user.subscriptions || user.favoriteLocations || user.favorite_locations || [];
                        // Normalize (lightweight) to ensure consistent keys for rendering
                        const subscriptions = (Array.isArray(rawSubscriptions) ? rawSubscriptions : []).map((s) => {
                            if (!s) return s;
                            // If this looks like the serialized subscription from backend (has id/station_id)
                            const station_id = s.station_id || s.stationId || s.station || s.id || s._id || (s._id ? String(s._id) : null) || null;
                            const station_name = s.station_name || s.nickname || s.name || s.title || s.label || null;
                            const created_at = s.createdAt || s.created_at || s.added_at || s.ts || null;
                            const current_aqi = (typeof s.current_aqi !== 'undefined' && s.current_aqi !== null) ? s.current_aqi : (typeof s.aqi !== 'undefined' && s.aqi !== null) ? s.aqi : (s.latest_reading?.aqi ?? null);
                            const threshold = (typeof s.threshold !== 'undefined' && s.threshold !== null) ? s.threshold : (typeof s.alert_threshold !== 'undefined' && s.alert_threshold !== null) ? s.alert_threshold : null;
                            const alert_enabled = (typeof s.alert_enabled !== 'undefined') ? s.alert_enabled : (typeof s.enabled !== 'undefined' ? s.enabled : (typeof s.status !== 'undefined' ? s.status === 'active' : false));
                            return Object.assign({}, s, {
                                station_id: station_id,
                                station_name: station_name,
                                created_at: created_at,
                                current_aqi: current_aqi,
                                threshold: threshold,
                                alert_enabled: alert_enabled
                            });
                        });
                        
                        // Debug logging to understand the API response structure
                        console.log('=== DEBUG: Admin Alerts Data ===');
                        console.log('Full user object:', user);
                        console.log('alertSettings:', alertSettings);
                        console.log('subscriptions/favoriteLocations:', subscriptions);
                        if (subscriptions.length > 0) {
                            console.log('First subscription object:', subscriptions[0]);
                            console.log('All subscription object keys:', Object.keys(subscriptions[0]));
                        }
                        console.log('=== END DEBUG ===');
                        
                        if (!subscriptions || subscriptions.length === 0) {
                                alertsContent.innerHTML = '<p class="text-muted">Người dùng chưa đăng ký trạm nào</p>';
                        } else {
                                let html = `<div class="mb-3"><h6 class="mb-0"><i class="fas fa-user me-2"></i><strong>Thông tin người dùng:</strong> ${fullname}</h6></div>`;
                subscriptions.forEach((location, idx) => {
                    console.log(`=== DEBUG: Location ${idx} ===`);
                    console.log('Location object:', location);
                    console.log('Location keys:', Object.keys(location));
                    console.log('location.created_at:', location.created_at);
                    console.log('location.added_at:', location.added_at);
                    console.log('location.current_aqi:', location.current_aqi);
                    console.log('location.aqi:', location.aqi);
                    console.log('location.latest_reading:', location.latest_reading);
                    console.log('location.threshold:', location.threshold);
                    console.log('location.alert_enabled:', location.alert_enabled);
                    console.log('=== END DEBUG ===');
                    
                    // Prefer normalized fields, but fall back to raw backend object if necessary
                    // Prefer readable name, then nickname, then station_id label, then generated index label
                    // Prefer friendly nickname/name/display_name over generic canonical labels
                    const rawLocName = (location && (location.nickname || location.name || location.display_name || location.canonical_display_name || location.station_name)) || (location.station_id ? (`Trạm ${location.station_id}`) : (location._raw ? this.getLocationName(location._raw, idx) : this.getLocationName(location, idx)));
                    const locName = this.escapeHtml(rawLocName);

                    // Use real data from API instead of mock data (check normalized then raw)
                    const registrationDateRaw = location.created_at || location.createdAt || location.added_at || (location._raw && (location._raw.createdAt || location._raw.created_at || location._raw.added_at));
                    const registrationDate = registrationDateRaw
                        ? new Date(registrationDateRaw).toLocaleDateString('vi-VN')
                        : 'N/A';

                    // Use real AQI from normalized location or raw subscription/station doc
                    const currentAQI = (typeof location.current_aqi !== 'undefined' && location.current_aqi !== null) ? location.current_aqi
                        : (typeof location.aqi !== 'undefined' && location.aqi !== null) ? location.aqi
                        : (location.latest_reading?.aqi ?? (location._raw && (location._raw.current_aqi ?? location._raw.aqi ?? location._raw.latest_reading?.aqi)) ?? null);
                    const numericAQI = (currentAQI !== null && typeof currentAQI !== 'undefined' && !isNaN(Number(currentAQI))) ? Number(currentAQI) : null;
                    const displayAQI = (numericAQI !== null) ? numericAQI : (currentAQI !== null && typeof currentAQI !== 'undefined' ? this.escapeHtml(currentAQI) : 'N/A');

                    // Use real threshold from normalized location or raw subscription (preserve 0)
                    const threshold = (typeof location.threshold !== 'undefined' && location.threshold !== null) ? location.threshold
                        : (typeof location.alert_threshold !== 'undefined' && location.alert_threshold !== null) ? location.alert_threshold
                        : (location._raw && (typeof location._raw.threshold !== 'undefined' && location._raw.threshold !== null ? location._raw.threshold : (typeof location._raw.alert_threshold !== 'undefined' && location._raw.alert_threshold !== null ? location._raw.alert_threshold : null)))
                        ?? (alertSettings?.thresholds?.pm25 ?? alertSettings?.threshold ?? 100);

                    // Use real alert enabled status (normalized then raw then default true)
                    const alertEnabled = (typeof location.alert_enabled !== 'undefined') ? location.alert_enabled : (location._raw && typeof location._raw.alert_enabled !== 'undefined' ? location._raw.alert_enabled : (location._raw && typeof location._raw.status !== 'undefined' ? location._raw.status === 'active' : false));
                    
                    // Determine AQI badge color based on actual value
                    let aqiBadgeClass = 'bg-secondary';
                    if (numericAQI !== null) {
                        if (numericAQI <= 50) {
                            aqiBadgeClass = 'bg-success';
                        } else if (numericAQI <= 100) {
                            aqiBadgeClass = 'bg-warning text-dark';
                        } else {
                            aqiBadgeClass = 'bg-danger';
                        }
                    }

                                        html += `
                                            <div class="card mb-3 subscription-card">
                                                <div class="card-body py-3">
                                                    <div class="d-flex align-items-center">
                                                        <div class="subscription-info flex-grow-1">
                                                            <h6 class="mb-1">${locName}</h6>
                                                            <div class="subscription-meta small text-muted">
                                                                <span class="me-3"><strong>Đăng ký:</strong> ${registrationDate}</span>
                                                                <span class="me-3"><strong>AQI:</strong> <span class="badge ${aqiBadgeClass}">${displayAQI}</span></span>
                                                                <span><strong>Ngưỡng:</strong> <span class="text-nowrap">${threshold}</span></span>
                                                            </div>
                                                        </div>
                                                        <div class="subscription-control text-end ms-3">
                                                            <div class="form-check form-switch">
                                                                <input class="form-check-input alert-toggle-inline" type="checkbox" ${alertEnabled ? 'checked' : ''} data-user-id="${id}" data-station="${(rawLocName || '').replace(/"/g, '&quot;')}" data-station-id="${location.station_id || location.stationId || ''}" data-sub-id="${location.id || location._id || ''}" id="alertToggleInline${idx}">
                                                                <label class="form-check-label" for="alertToggleInline${idx}"><i class="fas ${alertEnabled ? 'fa-bell' : 'fa-bell-slash'} me-1"></i><span class="ms-1 alert-label-text">${alertEnabled ? 'Bật' : 'Tắt'}</span></label>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        `;
                                });
                                alertsContent.innerHTML = html;

                                // Wire the inline toggles for UX
                                setTimeout(() => {
                                        document.querySelectorAll('.alert-toggle-inline').forEach(toggle => {
                                                toggle.addEventListener('change', async function(event) {
                                                        const t = event.target;
                                                        const userId = t.dataset.userId;
                                                        // Keep station name from dataset but fallback to heading if missing
                                                        let stationName = t.dataset.station;
                                                        if (!stationName || stationName === 'undefined') {
                                                            try {
                                                                const card = t.closest('.subscription-card');
                                                                const heading = card ? card.querySelector('.subscription-info h6, h6') : null;
                                                                stationName = heading && heading.textContent ? heading.textContent.trim() : stationName;
                                                            } catch (e) {}
                                                        }
                                                        let finalDisplayName = stationName;
                                                        const enabled = t.checked;
                                                        const label = t.nextElementSibling;
                                                        const icon = label?.querySelector('i');
                                                        
                                                        // Update UI optimistically
                                                        if (icon) icon.className = `fas ${enabled ? 'fa-bell' : 'fa-bell-slash'} me-1`;
                                                        const textSpan = label?.querySelector('.alert-label-text');
                                                        if (textSpan) textSpan.textContent = enabled ? 'Bật' : 'Tắt';
                                                        
                                                        // Save to server via admin API
                                                        try {
                                                            const token = this.getAuthToken();
                                                            if (!token) {
                                                                throw new Error('No auth token');
                                                            }
                                                            
                                                            // Find the subscription/location in the current user data
                                                            const modal = document.getElementById('userDetailModal');
                                                            const currentUser = modal.userData || user;
                                                            const dataSubId = t.getAttribute('data-sub-id');
                                                            const dataStationId = t.getAttribute('data-station-id');
                                                            let subscription = null;
                                                            if (dataSubId) {
                                                                subscription = (currentUser.subscriptions || []).find(s => String(s.id || s._id) === String(dataSubId)) ||
                                                                              (currentUser.favoriteLocations || []).find(loc => String(loc.id || loc._id || loc.sub_id || loc.subscription_id) === String(dataSubId));
                                                            }
                                                            if (!subscription && dataStationId) {
                                                                subscription = (currentUser.subscriptions || []).find(s => String(s.station_id) === String(dataStationId) || String(s.stationId) === String(dataStationId)) ||
                                                                              (currentUser.favoriteLocations || []).find(loc => String(loc.station_id) === String(dataStationId) || String(loc.stationId) === String(dataStationId));
                                                            }
                                                            if (!subscription) {
                                // Fallback to name matching against subscriptions then favorites
                                subscription = (currentUser.subscriptions || []).find(loc => (loc.station_name || loc.name) === stationName) ||
                                              (currentUser.favoriteLocations || []).find(loc => this.getLocationName(loc, 0) === stationName || loc.station_name === stationName || loc.name === stationName);
                            }
                                                            
                                                            if (subscription && typeof subscription === 'object') {
                            const resolvedDisplayName = subscription.station_name || subscription.name || subscription.nickname || (subscription._raw && (subscription._raw.station_name || subscription._raw.name));
                            if (resolvedDisplayName) {
                                finalDisplayName = resolvedDisplayName;
                                try { t.dataset.station = resolvedDisplayName; } catch (e) {}
                                                                // Update the card heading text so UI doesn't lose the station name
                                                                try {
                                                                    const card = t.closest('.subscription-card');
                                                                    const heading = card ? card.querySelector('.subscription-info h6, h6') : null;
                                                                    if (heading) heading.textContent = resolvedDisplayName;
                                                                } catch (e) {}
                            }
                        }
                        if (subscription || dataSubId || dataStationId) {
                                                                console.log('=== DEBUG: Alert Toggle API Call ===');
                                                                console.log('User ID:', userId);
                                                                console.log('New enabled state:', enabled);
                                                                console.log('Subscription object:', subscription);
                                                                console.log('dataSubId:', dataSubId, 'dataStationId:', dataStationId);

                                                                // Method 1: Try to update user's general notification preferences (best-effort)
                                                                try {
                                                                    const notifRes = await fetch(`/api/alerts/user/${userId}/notifications`, {
                                                                        method: 'PUT',
                                                                        headers: {
                                                                            'Content-Type': 'application/json',
                                                                            'Authorization': `Bearer ${token}`
                                                                        },
                                                                        body: JSON.stringify({
                                                                            enabled: enabled,
                                                                            threshold: (subscription && (subscription.threshold || subscription.alert_threshold)) || 100
                                                                        })
                                                                    });
                                                                    console.log('Notification update response:', notifRes.status);
                                                                } catch (e) {
                                                                    console.warn('Notification update failed (non-fatal):', e);
                                                                }

                                                                // Prefer updating by explicit subscription id if provided
                                                                if (dataSubId) {
                                                                    const updateRes = await fetch(`/api/alerts/subscriptions/${dataSubId}`, {
                                                                        method: 'PUT',
                                                                        headers: {
                                                                            'Content-Type': 'application/json',
                                                                            'Authorization': `Bearer ${token}`
                                                                        },
                                                                        body: JSON.stringify({
                                                                            status: enabled ? 'active' : 'paused',
                                                                            alert_threshold: (subscription && (subscription.threshold || subscription.alert_threshold)) || 100,
                                                                            metadata: { admin_updated: true }
                                                                        })
                                                                    });

                                                                    console.log('Subscription update (by sub id) response:', updateRes.status);
                                                                    if (!updateRes.ok) {
                                                                        throw new Error(`Subscription update failed: ${updateRes.status}`);
                                                                    }
                                                                } else {
                                                                    // Otherwise try to find by station id (prefer dataStationId if provided)
                                                                    const stationIdToUse = dataStationId || (subscription && (subscription.station_id || subscription.stationId));
                                                                    if (!stationIdToUse) {
                                                                        console.warn('No station id available to update/create subscription');
                                                                    } else {
                                                                        const subsRes = await fetch(`/api/alerts/subscriptions?user_id=${userId}&station_id=${stationIdToUse}`, {
                                                                            method: 'GET',
                                                                            headers: {
                                                                                'Content-Type': 'application/json',
                                                                                'Authorization': `Bearer ${token}`
                                                                            }
                                                                        });

                                                                        if (subsRes.ok) {
                                                                            const subsData = await subsRes.json();
                                                                            console.log('Found subscriptions:', subsData);

                                                                            if (subsData.subscriptions && subsData.subscriptions.length > 0) {
                                                                                // Update the first matching subscription
                                                                                const subId = subsData.subscriptions[0].id || subsData.subscriptions[0]._id;
                                                                                const updateRes = await fetch(`/api/alerts/subscriptions/${subId}`, {
                                                                                    method: 'PUT',
                                                                                    headers: {
                                                                                        'Content-Type': 'application/json',
                                                                                        'Authorization': `Bearer ${token}`
                                                                                    },
                                                                                    body: JSON.stringify({
                                                                                        status: enabled ? 'active' : 'paused',
                                                                                        alert_threshold: (subscription && (subscription.threshold || subscription.alert_threshold)) || 100,
                                                                                        metadata: { admin_updated: true }
                                                                                    })
                                                                                });

                                                                                console.log('Subscription update response:', updateRes.status);

                                                                                if (!updateRes.ok) {
                                                                                    throw new Error(`Subscription update failed: ${updateRes.status}`);
                                                                                }
                                                                            } else {
                                                                                // Create new subscription if none exists
                                                                                const createRes = await fetch('/api/alerts/subscriptions', {
                                                                                    method: 'POST',
                                                                                    headers: {
                                                                                        'Content-Type': 'application/json',
                                                                                        'Authorization': `Bearer ${token}`
                                                                                    },
                                                                                    body: JSON.stringify({
                                                                                        user_id: userId,
                                                                                        station_id: stationIdToUse,
                                                                                        alert_threshold: (subscription && (subscription.threshold || subscription.alert_threshold)) || 100,
                                                                                        status: enabled ? 'active' : 'paused',
                                                                                        metadata: { admin_created: true }
                                                                                    })
                                                                                });

                                                                                console.log('Subscription create response:', createRes.status);

                                                                                if (!createRes.ok) {
                                                                                    throw new Error(`Subscription creation failed: ${createRes.status}`);
                                                                                }
                                                                            }
                                                                        } else {
                                                                            console.warn('Could not fetch subscriptions:', subsRes.status);
                                                                        }
                                                                    }
                                                                }

                                                                // Update local data and persist resolved display name so future renders keep the name
                                                                if (subscription) {
                                                                    subscription.alert_enabled = enabled;
                                                                    try {
                                                                        // prefer preserving any existing server name but ensure a display name exists
                                                                        subscription.station_name = subscription.station_name || finalDisplayName || stationName || subscription.name || subscription.nickname;
                                                                        subscription.name = subscription.name || subscription.station_name;
                                                                        if (subscription._raw) subscription._raw.station_name = subscription._raw.station_name || subscription.station_name;
                                                                    } catch (e) {}
                                                                }

                                                                // Also update the modal's stored userData (subscriptions/favoriteLocations) so re-renders use the resolved name
                                                                try {
                                                                    const modal = document.getElementById('userDetailModal');
                                                                    if (modal && modal.userData) {
                                                                        const u = modal.userData;
                                                                        const updateArr = (arrName) => {
                                                                            const arr = u[arrName];
                                                                            if (!Array.isArray(arr)) return;
                                                                            for (const s of arr) {
                                                                                const sId = String(s.id || s._id || s.subscription_id || s.subscriptionId || s.subscription_id || s.station_id || '');
                                                                                const subId = String(subscription.id || subscription._id || subscription.subscription_id || subscription.station_id || '');
                                                                                if (sId && subId && sId === subId) {
                                                                                    s.station_name = subscription.station_name;
                                                                                    s.name = subscription.station_name;
                                                                                }
                                                                            }
                                                                        };
                                                                        updateArr('subscriptions');
                                                                        updateArr('favoriteLocations');
                                                                        updateArr('favorite_locations');
                                                                    }
                                                                } catch (e) {}

                                                                // Show success toast
                                                                if (typeof this.showToast === 'function') {
                                                                    this.showToast(`Đã ${enabled ? 'bật' : 'tắt'} cảnh báo cho trạm ${finalDisplayName || stationName}`, 'success');
                                                                } else if (window.showToast) {
                                                                    window.showToast(`Đã ${enabled ? 'bật' : 'tắt'} cảnh báo cho trạm ${finalDisplayName || stationName}`, 'success');
                                                                }
                                                            } else {
                                                                throw new Error('Không tìm thấy subscription để cập nhật');
                                                            }
                                                            
                                                        } catch (error) {
                                                            console.error('Error updating alert setting:', error);
                                                            // Revert UI on error
                                                            t.checked = !enabled;
                                                            if (icon) icon.className = `fas ${!enabled ? 'fa-bell' : 'fa-bell-slash'} me-1`;
                                                            if (textSpan) textSpan.textContent = !enabled ? 'Bật' : 'Tắt';
                                                            
                                                            // Show error toast
                                                            if (typeof this.showToast === 'function') {
                                                                this.showToast(`Lỗi: Không thể ${enabled ? 'bật' : 'tắt'} cảnh báo cho trạm ${finalDisplayName || stationName}. ${error.message}`, 'error');
                                                            } else if (window.showToast) {
                                                                window.showToast(`Lỗi: Không thể ${enabled ? 'bật' : 'tắt'} cảnh báo cho trạm ${finalDisplayName || stationName}`, 'error');
                                                            }
                                                        }
                                                }.bind(this));
                                        });
                                }, 50);
                        }
                }
    }

    renderUserLocations(locations) {
        const container = document.getElementById('userLocations');
        if (!container) return;

        if (locations.length === 0) {
            container.innerHTML = '<p class="text-muted">Người dùng chưa đăng ký địa điểm nào.</p>';
            return;
        }

        container.innerHTML = locations.map(location => `
            <div class="card mb-3">
                <div class="card-body">
                    <h6 class="card-title">${location.name}</h6>
                    <p class="card-text">
                        <small class="text-muted">
                            <i class="fas fa-map-marker-alt"></i> ${location.address}
                        </small>
                    </p>
                    <p class="card-text">
                        <small class="text-muted">
                            Đăng ký: ${new Date(location.created_at).toLocaleString('vi-VN')}
                        </small>
                    </p>
                </div>
            </div>
        `).join('');
    }

    renderUserAlerts(alertSettings) {
        const container = document.getElementById('userAlerts');
        if (!container) return;

        // Get the current user from the modal dataset - this contains real API data
        const userModal = document.getElementById('userDetailModal');
        const userId = userModal?.dataset.userId;
        
        // Find current user from either real data or fallback to mock
        let user = null;
        
        // First try to get from the modal's user data (real API data)
        if (userModal?.userData) {
            user = userModal.userData;
        } else {
            // Fallback to mock data
            user = this.mockUsers.find(u => u._id === userId);
        }
        
        if (!user || !user.favoriteLocations || user.favoriteLocations.length === 0) {
            container.innerHTML = '<p class="text-muted">Người dùng chưa đăng ký cảnh báo trạm nào.</p>';
            return;
        }

        // Use real data from API - each location contains actual subscription details
        // When both `subscriptions` and `favoriteLocations` exist, prefer the subscription
        // object for canonical display values (subscription-level names are authoritative).
        const subscriptions = (user.favoriteLocations || []).map((location, index) => {
            // Try to find a matching explicit subscription by id or station id
            let matchingSub = null;
            try {
                const subs = user.subscriptions || [];
                const locId = location.id || location._id || location.subscription_id || location.subscriptionId || null;
                const locStationId = location.station_id || location.stationId || null;
                if (Array.isArray(subs) && subs.length > 0) {
                    matchingSub = subs.find(s => {
                        const sId = s.id || s._id || s.subscription_id || s.subscriptionId || null;
                        const sStation = s.station_id || s.stationId || null;
                        if (sId && locId && String(sId) === String(locId)) return true;
                        if (sStation && locStationId && String(sStation) === String(locStationId)) return true;
                        return false;
                    }) || null;
                }
            } catch (e) {
                matchingSub = null;
            }
            // Extract real data from location object; prefer canonical server-provided names
            const rawName = location.station_name || location.name || location.display_name || location.displayName || this.getLocationName(location, index);
            const stationName = this.escapeHtml(rawName);
            // Try to grab a station id from likely fields so we can fetch full station if AQI missing
            const stationId = location.station_id || location.stationId || location.id || (location._raw && (location._raw.station_id || location._raw.id)) || (location._station && (location._station.station_id || location._station.id));
            const registrationDate = location.created_at 
                ? new Date(location.created_at).toLocaleDateString('vi-VN')
                : location.added_at 
                    ? new Date(location.added_at).toLocaleDateString('vi-VN')
                    : 'N/A';

            // Try a broader set of paths for AQI values to support varied backend shapes
            const rawAqiCandidates = [
                location.current_aqi,
                location.aqi,
                location.latest_reading && location.latest_reading.aqi,
                location.latest && location.latest.aqi,
                location.station && location.station.aqi,
                // server may attach a full station doc under _station
                location._station && location._station.latest_reading && location._station.latest_reading.aqi,
                location._station && location._station.latest && location._station.latest.aqi,
                // station doc may expose a top-level aqi or pollutant IAQI values
                location._station && typeof location._station.aqi !== 'undefined' ? location._station.aqi : null,
                location._station && location._station.pm25,
                // nested iaqi e.g. { iaqi: { pm25: { v: 12 } } }
                (location._station && location._station.iaqi && location._station.iaqi.pm25 && typeof location._station.iaqi.pm25.v !== 'undefined') ? location._station.iaqi.pm25.v : null,
                // raw subscription payload sometimes exists under _raw
                location._raw && location._raw.current_aqi,
                location._raw && location._raw.aqi,
                location._raw && location._raw.latest_reading && location._raw.latest_reading.aqi,
                location.latest?.value,
                location.value,
                location.currentValue
            ];

            let foundAqi = null;
            for (const c of rawAqiCandidates) {
                if (c !== undefined && c !== null && c !== '') {
                    foundAqi = c;
                    break;
                }
            }

            // DEBUG: log candidates and chosen value to help diagnose missing AQI
            try {
                console.debug('[AQI DEBUG] stationName:', stationName, 'rawAqiCandidates:', rawAqiCandidates, 'foundAqi:', foundAqi);
            } catch (e) {
                console.debug('[AQI DEBUG] could not stringify candidates');
            }

            // Coerce to number when possible; otherwise keep null to indicate missing
            const numericAQI = (foundAqi !== null && foundAqi !== undefined && !isNaN(Number(foundAqi))) ? Number(foundAqi) : null;
            // Display value: numeric if available, otherwise escaped string or 'N/A'
            const displayAQI = numericAQI !== null ? String(numericAQI) : (foundAqi !== null && foundAqi !== undefined ? this.escapeHtml(foundAqi) : 'N/A');

            // DEBUG: log numeric/display decision
            console.debug('[AQI DEBUG] stationName:', stationName, 'foundAqi:', foundAqi, 'numericAQI:', numericAQI, 'displayAQI:', displayAQI);

            // Use real threshold from location data
            const threshold = location.threshold || user.alertSettings?.thresholds?.pm25 || 100;

            // Use real alert enabled status
            const alertEnabled = (typeof location.alert_enabled !== 'undefined') ? location.alert_enabled : (typeof location.status !== 'undefined' ? location.status === 'active' : false);

            // If a matching subscription exists, prefer its station_name and keep local arrays in sync
            if (matchingSub && typeof matchingSub === 'object') {
                try {
                    const subName = matchingSub.station_name || matchingSub.name || matchingSub.display_name || matchingSub.nickname || null;
                    if (subName && subName !== location.station_name) {
                        // update the location object so subsequent renders use the canonical name
                        try { location.station_name = subName; } catch (e) {}
                        try { location.name = location.name || subName; } catch (e) {}
                        try { location.display_name = location.display_name || subName; } catch (e) {}
                    }
                } catch (e) {}
            }

            return {
                stationName: stationName,
                // also expose raw name for internal matching (unescaped)
                station_name: rawName,
                stationId,
                registrationDate,
                currentAQI: displayAQI,
                numericAQI,
                threshold,
                alertEnabled
            };
        });

        // Ensure we include any explicit user.subscriptions that are not present
        // in favoriteLocations. This preserves canonical subscription-level
        // station names (and other metadata) so toggling alerts doesn't lose
        // the display name.
        if (Array.isArray(user.subscriptions) && user.subscriptions.length > 0) {
            const presentKeys = new Set(subscriptions.map(s => String(s.subscription_id || s.stationId || s.station_id || '')));
                user.subscriptions.forEach((s, sidx) => {
                const sId = s.id || s._id || s.subscription_id || s.subscriptionId || null;
                const sStation = s.station_id || s.stationId || (s._raw && (s._raw.station_id || s._raw.id)) || null;
                const key = String(sId || sStation || '');
                if (!key) return;
                const existingIndex = subscriptions.findIndex(s => String(s.subscription_id || s.stationId || s.station_id || '') === key);
                // if an entry exists but key is present via other heuristics, allow replacement
                if (existingIndex === -1 && presentKeys.has(key)) return; // already represented

                const rawName = (s && (s.nickname || s.display_name || s.canonical_display_name || s.station_name || s.name)) || this.getLocationName(s, sidx);
                const stationName = this.escapeHtml(rawName);
                const stationId = s.station_id || s.stationId || s.id || (s._raw && (s._raw.station_id || s._raw.id)) || null;
                const registrationDate = s.created_at ? new Date(s.created_at).toLocaleDateString('vi-VN') : s.added_at ? new Date(s.added_at).toLocaleDateString('vi-VN') : 'N/A';

                const rawAqiCandidates = [
                    s.current_aqi,
                    s.aqi,
                    s.latest_reading && s.latest_reading.aqi,
                    s.latest && s.latest.aqi,
                    s.station && s.station.aqi,
                    s._station && s._station.latest_reading && s._station.latest_reading.aqi,
                    s._station && s._station.latest && s._station.latest.aqi,
                    s._station && typeof s._station.aqi !== 'undefined' ? s._station.aqi : null,
                    s._station && s._station.pm25,
                    (s._station && s._station.iaqi && s._station.iaqi.pm25 && typeof s._station.iaqi.pm25.v !== 'undefined') ? s._station.iaqi.pm25.v : null,
                    s._raw && s._raw.current_aqi,
                    s._raw && s._raw.aqi,
                    s._raw && s._raw.latest_reading && s._raw.latest_reading.aqi,
                    s.latest?.value,
                    s.value,
                    s.currentValue
                ];
                let foundAqi = null;
                for (const c of rawAqiCandidates) {
                    if (c !== undefined && c !== null && c !== '') { foundAqi = c; break; }
                }
                const numericAQI = (foundAqi !== null && foundAqi !== undefined && !isNaN(Number(foundAqi))) ? Number(foundAqi) : null;
                const displayAQI = numericAQI !== null ? String(numericAQI) : (foundAqi !== null && foundAqi !== undefined ? this.escapeHtml(foundAqi) : 'N/A');
                const threshold = s.threshold || user.alertSettings?.thresholds?.pm25 || 100;
                const alertEnabled = (typeof s.alert_enabled !== 'undefined') ? s.alert_enabled : (typeof s.status !== 'undefined' ? s.status === 'active' : false);

                const enriched = {
                    stationName: stationName,
                    station_name: rawName,
                    stationId,
                    registrationDate,
                    currentAQI: displayAQI,
                    numericAQI,
                    threshold,
                    alertEnabled,
                    subscription_id: sId
                };
                if (existingIndex >= 0) {
                    // Replace the existing (likely favorite-derived) entry with subscription-level data
                    subscriptions[existingIndex] = enriched;
                    presentKeys.add(key);
                } else {
                    subscriptions.push(enriched);
                    presentKeys.add(key);
                }
        
            });
        }

        // Post-process names: sometimes subscriptions contain generic codes like "Trạm 8688"
        // while other entries have a richer display_name. Build a name map keyed by
        // stationId or subscription_id and pick the most meaningful name.
        const nameMap = {};
        const meaningfulRegex = /^\s*(TRAM|TRẠM)\s*\d+\s*$/i;
        const scoreName = (n) => {
            if (!n || typeof n !== 'string') return 0;
            const t = n.trim();
            if (meaningfulRegex.test(t)) return 1; // low score for generic codes
            return Math.min(100, t.length + 10); // longer names get higher score
        };
        subscriptions.forEach(s => {
            const key = String(s.subscription_id || s.stationId || s.station_id || '');
            const candidate = (s.station_name || s.stationName || '').trim();
            if (!key) return;
            const prev = nameMap[key];
            if (!prev || scoreName(candidate) > scoreName(prev)) {
                nameMap[key] = candidate;
            }
        });

        // Also check raw user.subscriptions array for richer names in case some
        // subscription objects weren't normalized yet.
        if (Array.isArray(user.subscriptions)) {
            user.subscriptions.forEach(s => {
                const key = String(s.id || s._id || s.subscription_id || s.station_id || s.stationId || '');
                const candidate = (s.display_name || s.station_name || s.name || s.nickname || '').trim();
                if (!key) return;
                const prev = nameMap[key];
                if (!prev || scoreName(candidate) > scoreName(prev)) {
                    nameMap[key] = candidate;
                }
            });
        }

        // Apply the best name back to subscription display fields
        subscriptions.forEach(s => {
            const key = String(s.subscription_id || s.stationId || s.station_id || '');
            const best = nameMap[key];
            if (best && best !== '' && !/^\s*(TRAM|TRẠM)\s*\d+\s*$/i.test(best)) {
                s.station_name = best;
                s.stationName = this.escapeHtml(best);
            }
        });

        let html = `<div class="mb-3">
            <h6 class="mb-0"><i class="fas fa-user me-2"></i><strong>Thông tin người dùng:</strong> ${user.fullname || user.username}</h6>
        </div>`;

        subscriptions.forEach((sub, index) => {
            // Determine AQI badge color based on actual value
            // Map AQI numeric ranges to badge classes. If numericAQI is null, use neutral bg-secondary
            let aqiBadgeClass = 'bg-secondary';
            if (typeof sub.numericAQI === 'number') {
                if (sub.numericAQI <= 50) {
                    aqiBadgeClass = 'bg-success';
                } else if (sub.numericAQI <= 100) {
                    aqiBadgeClass = 'bg-warning text-dark';
                } else if (sub.numericAQI <= 150) {
                    aqiBadgeClass = 'bg-danger';
                } else {
                    // Very unhealthy / hazardous
                    aqiBadgeClass = 'bg-dark text-white';
                }
            }

            html += `
                <div class="card mb-3 subscription-card">
                    <div class="card-body py-3">
                        <div class="d-flex align-items-center">
                            <div class="subscription-info flex-grow-1">
                                <h6 class="mb-1">${sub.stationName}</h6>
                                <div class="subscription-meta small text-muted">
                                    <span class="me-3"><strong>Đăng ký:</strong> ${sub.registrationDate}</span>
                                    <span class="me-3"><strong>AQI:</strong> <span class="badge ${aqiBadgeClass}">${sub.currentAQI}</span></span>
                                    <span><strong>Ngưỡng:</strong> <span class="text-nowrap">${sub.threshold}</span></span>
                                </div>
                            </div>

                            <div class="subscription-control text-end ms-3 d-flex align-items-center justify-content-end">
                                <div class="me-2">
                                    <button class="btn btn-sm btn-outline-secondary edit-subscription-name" data-sub-id="${sub.subscription_id || sub.id || ''}" data-current-name="${(sub.station_name || '').replace(/"/g, '&quot;')}"><i class="fas fa-edit"></i></button>
                                </div>
                                <div>
                                    <div class="form-check form-switch">
                     <input class="form-check-input alert-toggle" type="checkbox" 
                         ${sub.alertEnabled ? 'checked' : ''} 
                         data-user-id="${userId}" 
                         data-station-id="${sub.stationId || sub.station_id || ''}"
                         data-sub-id="${sub.subscription_id || sub.id || ''}"
                         data-station="${(sub.station_name || '').replace(/"/g, '&quot;')}"
                         id="alertToggle${index}">
                                    <label class="form-check-label" for="alertToggle${index}">
                                        <i class="fas ${sub.alertEnabled ? 'fa-bell' : 'fa-bell-slash'} me-1"></i>
                                        <span class="ms-1 alert-label-text">${sub.alertEnabled ? 'Bật' : 'Tắt'}</span>
                                    </label>
                                </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            // If AQI is missing (display 'N/A') but we have a stationId, try a non-blocking client-side fetch
            if ((sub.currentAQI === 'N/A' || sub.numericAQI === null) && sub.stationId) {
                // schedule a microtask to avoid blocking render
                (async (stationId, cardIndex) => {
                    try {
                        console.debug('[AQI FETCH] attempting fetch for station', stationId);
                        const token = this.getAuthToken ? this.getAuthToken() : null;
                        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
                        const resp = await fetch(`/api/stations/${encodeURIComponent(stationId)}`, { headers });
                        if (!resp.ok) {
                            console.debug('[AQI FETCH] station fetch failed', resp.status);
                            return;
                        }
                        const stationData = await resp.json();
                        // Try to find an AQI in returned station doc
                        const stationAqi = stationData?.latest_reading?.aqi ?? stationData?.aqi ?? stationData?.latest?.aqi ?? (stationData?.iaqi?.pm25?.v ?? null);
                        if (stationAqi !== undefined && stationAqi !== null && stationAqi !== '') {
                            const numeric = !isNaN(Number(stationAqi)) ? Number(stationAqi) : null;
                            const disp = numeric !== null ? String(numeric) : String(stationAqi);
                            // Find the corresponding badge in the modal and update it
                            try {
                                const badges = document.querySelectorAll('#userAlerts .subscription-card');
                                const card = badges[cardIndex];
                                if (card) {
                                    const badgeEl = card.querySelector('.badge');
                                    if (badgeEl) {
                                        badgeEl.textContent = disp;
                                        // update badge class based on numeric value
                                        if (numeric !== null) {
                                            badgeEl.className = 'badge ' + (numeric <= 50 ? 'bg-success' : numeric <= 100 ? 'bg-warning text-dark' : numeric <= 150 ? 'bg-danger' : 'bg-dark text-white');
                                        }
                                    }
                                }
                                console.debug('[AQI FETCH] updated badge for station', stationId, 'value', disp);
                            } catch (e) {
                                console.debug('[AQI FETCH] failed to update DOM', e);
                            }
                        }
                    } catch (e) {
                        console.debug('[AQI FETCH] error fetching station', stationId, e);
                    }
                })(sub.stationId, index);
            }
        });

        container.innerHTML = html;

        // Post-render: attempt to enrich generic names (e.g., 'Trạm 13665') by fetching station docs
        (async () => {
            try {
                const genericRe = /^\s*(TRAM|TRẠM)\s*\d+\s*$/i;
                const token = this.getAuthToken ? this.getAuthToken() : null;
                const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
                // iterate subscriptions again to find generic names to enrich
                subscriptions.forEach(async (sub, idx) => {
                    try {
                        const nameCandidate = (sub.station_name || sub.stationName || '') + '';
                        if (!genericRe.test(nameCandidate)) return; // only enrich generic labels
                        const stationId = sub.stationId || sub.station_id || sub.subscription_id || null;
                        if (!stationId) return;
                        const resp = await fetch(`/api/stations/${encodeURIComponent(stationId)}`, { headers });
                        if (!resp.ok) return;
                        const stationData = await resp.json();
                        const payload = stationData && stationData.station ? stationData.station : stationData;
                        if (!payload) return;
                        // pick friendly name from station payload
                        const candFields = [payload.nickname, payload.display_name, payload.canonical_display_name, payload.name, payload.title, payload.meta?.name, payload.properties?.name, payload.location, payload.label];
                        let best = null;
                        for (const c of candFields) {
                            if (!c || typeof c !== 'string') continue;
                            const t = c.trim();
                            if (!t) continue;
                            if (/^\s*(TRAM|TRẠM)\s*\d+\s*$/i.test(t)) continue;
                            best = t; break;
                        }
                        if (!best) {
                            // fallback to any non-empty field
                            for (const c of candFields) { if (c && typeof c === 'string' && c.trim()) { best = c.trim(); break; } }
                        }
                        if (!best) return;
                        // Update DOM card heading
                        try {
                            const cards = document.querySelectorAll('#userAlerts .subscription-card');
                            const card = cards[idx];
                            if (card) {
                                const heading = card.querySelector('.subscription-info h6, h6');
                                if (heading) heading.textContent = best;
                                const dataStationEl = card.querySelector('.form-check-input.alert-toggle');
                                if (dataStationEl) dataStationEl.dataset.station = best;
                            }
                        } catch (e) {}
                        // Persist into modal.userData arrays so future renders keep the friendly name
                        try {
                            const modal = document.getElementById('userDetailModal');
                            if (modal && modal.userData) {
                                const u = modal.userData;
                                const updateArr = (arrName) => {
                                    const arr = u[arrName]; if (!Array.isArray(arr)) return;
                                    for (const s of arr) {
                                        if (!s || typeof s !== 'object') continue;
                                        const sKey = String(s.id || s._id || s.subscription_id || s.station_id || s.stationId || '');
                                        const subKey = String(sub.subscription_id || sub.id || sub.stationId || sub.station_id || '');
                                        if (sKey && subKey && sKey === subKey) {
                                            try { s.station_name = best; s.name = s.name || best; s.display_name = s.display_name || best; if (s._raw && typeof s._raw === 'object') s._raw.station_name = s._raw.station_name || best; } catch (e) {}
                                        }
                                    }
                                };
                                updateArr('subscriptions'); updateArr('favoriteLocations'); updateArr('favorite_locations');
                            }
                        } catch (e) {}
                    } catch (e) {
                        // ignore per-station failures
                    }
                });
            } catch (e) {
                console.debug('[NAME ENRICH] unexpected error', e);
            }
        })();

        // Add event listeners for alert toggles (local-only, no API calls)
        container.querySelectorAll('.alert-toggle').forEach(toggle => {
            toggle.addEventListener('change', this.handleAlertToggle.bind(this));
        });

        // Wire edit button handlers for friendly station name
        container.querySelectorAll('.edit-subscription-name').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const b = e.currentTarget;
                const subId = b.dataset.subId;
                const current = b.dataset.currentName || '';
                const newName = prompt('Nhập tên hiển thị cho trạm (nickname):', current || '');
                if (newName === null) return; // cancelled
                const friendly = (newName || '').trim();
                if (!friendly) {
                    alert('Tên không được để trống');
                    return;
                }

                // Optimistic UI update
                try {
                    const card = b.closest('.subscription-card');
                    if (card) {
                        const heading = card.querySelector('.subscription-info h6, h6');
                        if (heading) heading.textContent = friendly;
                        const input = card.querySelector('.form-check-input.alert-toggle');
                        if (input) input.dataset.station = friendly;
                    }

                    // Update modal.userData arrays
                    const modal = document.getElementById('userDetailModal');
                    if (modal && modal.userData) {
                        const u = modal.userData;
                        const arrs = ['subscriptions','favoriteLocations','favorite_locations'];
                        for (const a of arrs) {
                            const arr = u[a];
                            if (!Array.isArray(arr)) continue;
                            for (const s of arr) {
                                if (!s || typeof s !== 'object') continue;
                                const key = String(s.id || s._id || s.subscription_id || s.station_id || s.stationId || '');
                                if (!key) continue;
                                if (subId && key === String(subId)) {
                                    try { s.station_name = friendly; s.name = s.name || friendly; s.display_name = s.display_name || friendly; if (s._raw && typeof s._raw === 'object') s._raw.station_name = s._raw.station_name || friendly; } catch (e){}
                                }
                            }
                        }
                    }

                    // Persist to server if subscription id present
                    if (subId) {
                        try {
                            const token = this.getAuthToken ? this.getAuthToken() : null;
                            const headers = { 'Content-Type': 'application/json' };
                            if (token) headers['Authorization'] = `Bearer ${token}`;
                            const resp = await fetch(`/api/alerts/subscriptions/${encodeURIComponent(subId)}`, {
                                method: 'PUT',
                                headers,
                                body: JSON.stringify({ station_name: friendly, display_name: friendly, name: friendly })
                            });
                            if (!resp.ok) {
                                const txt = await resp.text();
                                throw new Error(`HTTP ${resp.status}: ${txt}`);
                            }
                            if (typeof this.showToast === 'function') this.showToast('Đã lưu tên trạm', 'success');
                        } catch (e) {
                            console.error('Failed to persist friendly name', e);
                            if (typeof this.showToast === 'function') this.showToast('Không thể lưu tên trạm lên server', 'error');
                        }
                    }
                } catch (e) {
                    console.error('Error setting friendly name', e);
                }
            });
        });
    }

    async handleAlertToggle(event) {
        const toggle = event.target;
        const userId = toggle.dataset.userId;
        // Prefer dataset value but fall back to card heading text to avoid losing name
        let stationName = toggle.dataset.station;
        if (!stationName || stationName === 'undefined') {
            try {
                const card = toggle.closest('.subscription-card');
                const heading = card ? card.querySelector('.subscription-info h6, h6') : null;
                stationName = heading && heading.textContent ? heading.textContent.trim() : stationName;
            } catch (e) {
                // ignore and keep original dataset value
            }
        }
        const isEnabled = toggle.checked;
        // Update the label and icon immediately for better UX (local-only)
        const label = toggle.nextElementSibling;
        const icon = label?.querySelector('i');
        if (icon) {
            icon.className = `fas ${isEnabled ? 'fa-bell' : 'fa-bell-slash'} me-1`;
        }
        const textSpan = label?.querySelector('.alert-label-text');
        if (textSpan) {
            textSpan.textContent = isEnabled ? 'Bật' : 'Tắt';
        } else if (label) {
            // fallback: rebuild label content
            // Rebuild only the label contents (do not touch other card elements)
            label.innerHTML = `<i class="fas ${isEnabled ? 'fa-bell' : 'fa-bell-slash'} me-1"></i><span class="ms-1 alert-label-text">${isEnabled ? 'Bật' : 'Tắt'}</span>`;
        }

        // NOTE: per request, do NOT call the admin alerts API from the admin UI.
        // The alert toggle in the admin detail view is now local-only. If you want
        // this to call a user-scoped API later, tell me which endpoint to use and
        // I'll wire it to that API (including CSRF/auth headers).
        console.log(`Alert toggle (local-only) for user ${userId}, station ${stationName}: ${isEnabled}`);
        this.showToast(`Đã ${isEnabled ? 'bật' : 'tắt'} cảnh báo cho trạm ${stationName}`, 'info');
        // Persist name into modal.userData if available so subsequent JS re-renders keep the name
        try {
            const modal = document.getElementById('userDetailModal');
            if (modal && modal.userData) {
                const u = modal.userData;
                const dataSubId = toggle.getAttribute('data-sub-id');
                const dataStationId = toggle.getAttribute('data-station-id');

                // Helper to attempt to update an array of subscriptions/locations
                const tryUpdateArray = (arr) => {
                    if (!Array.isArray(arr)) return false;
                    let matched = false;
                    for (const s of arr) {
                        if (!s || typeof s !== 'object') continue;

                        // Normalize various id fields for matching
                        const sIds = [s.id, s._id, s.subscription_id, s.subscriptionId, s.sub_id, s.station_id, s.stationId].map(x => typeof x !== 'undefined' && x !== null ? String(x) : null).filter(Boolean);
                        const stationIdStr = s.station_id || s.stationId || (s._raw && (s._raw.station_id || s._raw.stationId)) || null;

                        const matchesSubId = dataSubId && sIds.includes(String(dataSubId));
                        const matchesStationId = dataStationId && (String(stationIdStr) === String(dataStationId) || sIds.includes(String(dataStationId)));
                        const matchesByName = (s.station_name && String(s.station_name) === String(stationName)) || (s.name && String(s.name) === String(stationName)) || (String(this.getLocationName(s, 0)) === String(stationName));

                        if (matchesSubId || matchesStationId || matchesByName) {
                            try {
                                s.station_name = stationName;
                                s.name = s.name || stationName;
                                s.display_name = s.display_name || stationName;
                                if (s._raw && typeof s._raw === 'object') s._raw.station_name = s._raw.station_name || stationName;
                            } catch (e) {}
                            matched = true;
                        }
                    }
                    return matched;
                };

                // Try to update common arrays used by the UI
                const arraysToUpdate = ['subscriptions', 'favoriteLocations', 'favorite_locations'];
                let anyMatched = false;
                for (const aName of arraysToUpdate) {
                    try {
                        const arr = u[aName];
                        if (tryUpdateArray(arr)) anyMatched = true;
                    } catch (e) {}
                }

                // If nothing matched, attempt a best-effort append to favoriteLocations so the name is preserved locally
                if (!anyMatched) {
                    try {
                        u.favoriteLocations = u.favoriteLocations || u.favorite_locations || [];
                        u.favoriteLocations.push({ station_id: dataStationId || null, station_name: stationName, name: stationName, created_at: new Date().toISOString() });
                        // Keep alias for other arrays as well
                        u.favorite_locations = u.favorite_locations || u.favoriteLocations;
                    } catch (e) {}
                }

                // Update the toggle element's dataset so future reads get the resolved value
                try { toggle.dataset.station = stationName; } catch (e) {}
                // If we have a subscription id, persist the friendly name to the server
                // so the canonical name is stored on the subscription document. The
                // alerts API accepts station_name updates via PUT and is safe for
                // admin workflows (no auth required for this endpoint in backend).
                const persistIfPossible = async () => {
                    if (!dataSubId) return;
                    try {
                        const token = this.getAuthToken ? this.getAuthToken() : null;
                        const headers = { 'Content-Type': 'application/json' };
                        if (token) headers['Authorization'] = `Bearer ${token}`;

                        // Persist the friendly name on the subscription
                        const resp = await fetch(`/api/alerts/subscriptions/${encodeURIComponent(dataSubId)}`, {
                            method: 'PUT',
                            headers,
                            body: JSON.stringify({
                                station_name: stationName,
                                display_name: stationName,
                                name: stationName,
                                metadata: { nickname: stationName }
                            })
                        });

                        if (!resp.ok) {
                            console.debug('[ADMIN TOGGLE] failed to persist subscription name', await resp.text());
                            return;
                        }

                        // Re-fetch canonical user locations from admin API so we render
                        // authoritative subscription names (this avoids stale favorite-derived names)
                                if (token && userId) {
                                    try {
                                        // Correct admin locations endpoint: /api/admin/users/<user_id>/locations
                                        const locResp = await fetch(`/api/admin/users/${encodeURIComponent(userId)}/locations?include_expired=1`, {
                                            method: 'GET',
                                            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
                                        });
                                if (locResp.ok) {
                                            const json = await locResp.json();
                                            // Merge server response into modal.userData but prefer any
                                            // existing non-generic (friendly) names already shown in the UI.
                                            try {
                                                modal.userData = modal.userData || {};
                                                const serverFavorites = json.favoriteLocations || json.favorite_locations || [];
                                                const serverSubscriptions = json.subscriptions || [];

                                                const normalizeGenericLabel = (name) => {
                                                    if (!name || typeof name !== 'string') return '';
                                                    return name
                                                        .normalize('NFD')
                                                        .replace(/[\u0300-\u036f]/g, '')
                                                        .replace(/\u0111/g, 'd')
                                                        .replace(/\u0110/g, 'D')
                                                        .toUpperCase()
                                                        .replace(/\s+/g, ' ')
                                                        .trim();
                                                };
                                                const isGeneric = (n) => {
                                                    if (!n || typeof n !== 'string') return false;
                                                    const normalized = normalizeGenericLabel(n);
                                                    return /^(TRAM|STATION)(?:[\s\-_/])*\d+$/.test(normalized);
                                                };

                                                const pickBestName = (localName, serverName) => {
                                                    // Prefer the local friendly name when available (admin just edited it).
                                                    // Fall back to server-provided name only when local name is missing or generic.
                                                    if (localName && !isGeneric(localName)) return localName;
                                                    if (serverName && !isGeneric(serverName)) return serverName;
                                                    // fallback to serverName if present, else localName
                                                    return serverName || localName || null;
                                                };

                                                const mergeArrays = (localArr, serverArr, keyFields = ['id','_id','subscription_id','station_id','stationId']) => {
                                                    const out = [];
                                                    const seen = new Set();
                                                    const findKey = (item) => {
                                                        if (!item || typeof item !== 'object') return null;
                                                        for (const k of keyFields) {
                                                            if (item[k]) return String(item[k]);
                                                        }
                                                        return null;
                                                    };

                                                    // Index local by key
                                                    const localMap = new Map();
                                                    if (Array.isArray(localArr)) {
                                                        for (const l of localArr) {
                                                            const k = findKey(l);
                                                            if (k) localMap.set(k, l);
                                                        }
                                                    }

                                                    // Merge server items, prefer best names
                                                    if (Array.isArray(serverArr)) {
                                                        for (const s of serverArr) {
                                                            const k = findKey(s) || findKey(s._raw) || null;
                                                            let local = k ? localMap.get(k) : null;
                                                            const localName = local ? (local.station_name || local.name || local.display_name) : null;
                                                            const serverName = s.station_name || s.name || s.display_name || (s.metadata && s.metadata.nickname) || null;
                                                            const chosen = pickBestName(localName, serverName);
                                                            const merged = Object.assign({}, local || {}, s || {});
                                                            if (chosen) {
                                                                try { merged.station_name = chosen; merged.name = merged.name || chosen; merged.display_name = merged.display_name || chosen; } catch (e) {}
                                                            }
                                                            out.push(merged);
                                                            if (k) seen.add(k);
                                                        }
                                                    }

                                                    // Append any local-only items that server didn't return
                                                    if (Array.isArray(localArr)) {
                                                        for (const l of localArr) {
                                                            const k = findKey(l);
                                                            if (k && seen.has(k)) continue;
                                                            out.push(l);
                                                        }
                                                    }

                                                    return out;
                                                };

                                                // Merge favorites and subscriptions, preserving friendly local names
                                                modal.userData.favoriteLocations = mergeArrays(modal.userData.favoriteLocations || [], serverFavorites, ['station_id','stationId','id','_id']);
                                                modal.userData.subscriptions = mergeArrays(modal.userData.subscriptions || [], serverSubscriptions, ['id','_id','subscription_id','station_id','stationId']);
                                                modal.userData.alertSettings = json.alertSettings || json.alert_settings || modal.userData.alertSettings;
                                            } catch (e) {
                                                console.debug('[ADMIN TOGGLE] failed to merge server locations', e);
                                            }
                                        } else {
                                            // Preserve local friendly names and inform the admin that refresh failed
                                            try {
                                                const serverBody = await locResp.text();
                                                console.debug('[ADMIN TOGGLE] failed to reload user locations', locResp.status, serverBody);
                                            } catch (e) {
                                                console.debug('[ADMIN TOGGLE] failed to reload user locations', locResp.status);
                                            }
                                            if (typeof this.showToast === 'function') {
                                                this.showToast('Không thể làm mới tên trạm từ server — tên cục bộ đã được giữ.', 'error');
                                            }
                                            // Do not attempt to merge or replace modal.userData when the server returns an error
                                            return;
                                        }
                            } catch (e) {
                                console.debug('[ADMIN TOGGLE] error fetching admin user locations', e);
                            }
                        }

                    } catch (e) {
                        console.debug('[ADMIN TOGGLE] error persisting subscription name', e);
                    }
                };

                // Fire-and-forget persistence and canonical refresh, but re-render immediately for UX
                persistIfPossible();

                // Re-render the alerts pane from the updated modal.userData so the visible heading is stable
                try {
                    const currentAlertSettings = u.alertSettings || u.alert_settings || {};
                    this.renderUserAlerts(currentAlertSettings);
                } catch (e) {}
            }
        } catch (e) {}
    }

    async exportToCSV() {
        try {
            this.showLoading(true);

            // Generate CSV from mock data instead of API call
            const searchTerm = document.getElementById('userSearch')?.value.toLowerCase() || '';
            const statusFilter = document.getElementById('statusFilter')?.value || '';
            
            let exportUsers = this.selectedUsers.size > 0 
                ? this.mockUsers.filter(user => this.selectedUsers.has(user._id))
                : this.mockUsers;
            
            // Apply filters to export data
            if (searchTerm) {
                exportUsers = exportUsers.filter(user => 
                    user.username.toLowerCase().includes(searchTerm) ||
                    user.email.toLowerCase().includes(searchTerm) ||
                    user.fullname.toLowerCase().includes(searchTerm)
                );
            }
            
            if (statusFilter === 'active') {
                exportUsers = exportUsers.filter(user => user.isActive);
            } else if (statusFilter === 'inactive') {
                exportUsers = exportUsers.filter(user => !user.isActive);
            }

            // Generate CSV content
            const csvHeaders = ['ID', 'Tên đăng nhập', 'Email', 'Họ tên', 'Vai trò', 'Trạng thái', 'Email đã xác thực', 'Ngày tạo', 'Địa điểm yêu thích'];
            const csvRows = exportUsers.map(user => [
                user._id,
                user.username,
                user.email,
                user.fullname,
                user.role,
                user.isActive ? 'Hoạt động' : 'Không hoạt động',
                user.emailVerified ? 'Đã xác thực' : 'Chưa xác thực',
                new Date(user.createdAt).toLocaleDateString('vi-VN'),
                user.favoriteLocations.join('; ')
            ]);

            const csvContent = [csvHeaders, ...csvRows]
                .map(row => row.map(field => `"${field}"`).join(','))
                .join('\n');

            // Create and download file
            const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `users_export_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showSuccess('Đã xuất file CSV thành công');
        } catch (error) {
            console.error('CSV export error:', error);
            this.showError('Lỗi xuất file CSV');
        } finally {
            this.showLoading(false);
        }
    }

    // Utility methods
    getAuthToken() {
        // Try to get token from localStorage, sessionStorage, or cookie
     return localStorage.getItem('access_token') || 
         sessionStorage.getItem('access_token') || 
         this.getCookie('access_token') || 
         null;
    }

    setAuthToken(token) {
        // Store token in localStorage for persistence
        localStorage.setItem('access_token', token);
    }

    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    getCSRFToken() {
        const token = document.querySelector('meta[name="csrf-token"]');
        return token ? token.getAttribute('content') : '';
    }

    showLoading(show) {
        const loadingSpinner = document.getElementById('loadingSpinner');
        if (loadingSpinner) {
            loadingSpinner.style.display = show ? 'block' : 'none';
        }
    }

    showSuccess(message) {
        this.showToast(message, 'success');
    }

    showError(message) {
        this.showToast(message, 'error');
    }

    showToast(message, type) {
        // Create toast element
        const toastContainer = document.getElementById('toastContainer') || this.createToastContainer();
        
        const toastId = 'toast-' + Date.now();
        const toastHTML = `
            <div id="${toastId}" class="toast align-items-center text-white bg-${type === 'success' ? 'success' : 'danger'} border-0" role="alert">
                <div class="d-flex">
                    <div class="toast-body">
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHTML);
        
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement);
        toast.show();

        // Remove toast element after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1055';
        document.body.appendChild(container);
        return container;
    }

    async showConfirmDialog(title, message) {
        return new Promise((resolve) => {
            // Create modal if not exists
            let modal = document.getElementById('confirmModal');
            if (!modal) {
                modal = this.createConfirmModal();
            }

            // Update modal content
            modal.querySelector('#confirmModalLabel').textContent = title;
            modal.querySelector('#confirmModalBody').textContent = message;

            // Set up event listeners
            const confirmBtn = modal.querySelector('#confirmBtn');
            const cancelBtn = modal.querySelector('#cancelBtn');

            const cleanup = () => {
                confirmBtn.removeEventListener('click', onConfirm);
                cancelBtn.removeEventListener('click', onCancel);
                modal.removeEventListener('hidden.bs.modal', onHidden);
            };

            const onConfirm = () => {
                cleanup();
                resolve(true);
                bootstrap.Modal.getInstance(modal).hide();
            };

            const onCancel = () => {
                cleanup();
                resolve(false);
                bootstrap.Modal.getInstance(modal).hide();
            };

            const onHidden = () => {
                cleanup();
                resolve(false);
            };

            confirmBtn.addEventListener('click', onConfirm);
            cancelBtn.addEventListener('click', onCancel);
            modal.addEventListener('hidden.bs.modal', onHidden);

            // Show modal
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();
        });
    }

    createConfirmModal() {
        const modalHTML = `
            <div class="modal fade" id="confirmModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="confirmModalLabel">Xác nhận</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body" id="confirmModalBody">
                            Bạn có chắc chắn muốn thực hiện hành động này?
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" id="cancelBtn">Hủy</button>
                            <button type="button" class="btn btn-danger" id="confirmBtn">Xác nhận</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHTML);
        return document.getElementById('confirmModal');
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('[admin_user_management.js] DOMContentLoaded - initializing AdminUserManagement');
    window.__adminUserManagement = new AdminUserManagement();
});

// Global helper for template button
function bulkChangeStatus() {
    if (window.__adminUserManagement) {
        window.__adminUserManagement.bulkChangeStatus();
    } else {
        alert('Quản lý người dùng chưa sẵn sàng');
    }
}

/*
 * Backward-compatible global wrappers for legacy template onclick handlers.
 * These expose `editUser()` and `saveUserChanges()` globally so the template
 * buttons continue to work while the class-based system is used.
 */
function editUser() {
    try {
        const detailModal = document.getElementById('userDetailModal');
        let currentUserId = detailModal?.dataset.userId;

        // Fallback: if dataset not set, try to parse ID from basic info content (#ID)
        if (!currentUserId) {
            try {
                const basic = document.getElementById('basicInfoContent');
                if (basic) {
                    // Find the row label that contains 'ID' and take its value
                    const rows = basic.querySelectorAll('.user-info-row');
                    for (const row of rows) {
                        const label = row.querySelector('.user-info-label');
                        const value = row.querySelector('.user-info-value');
                        if (label && value && /ID/i.test(label.textContent || '')) {
                            currentUserId = (value.textContent || '').replace(/^#/, '').trim();
                            if (currentUserId) break;
                        }
                    }
                }
            } catch (err) {
                console.warn('Failed parsing ID from basicInfoContent', err);
            }
        }
        const manager = window.__adminUserManagement;

        // Prefer class method if present
        if (manager && typeof manager.openEditModal === 'function') {
            return manager.openEditModal(currentUserId);
        }

        // Otherwise populate edit form from manager.mockUsers or HTML in-place
        let user = null;
        if (manager && Array.isArray(manager.mockUsers)) {
            user = manager.mockUsers.find(u => {
                const a = String(u._id || u.id || '');
                const b = String(currentUserId || '');
                return a === b;
            });
        }

        if (!user) {
            // Try to fetch from API as fallback (include auth if available)
            try {
                const token = (manager && typeof manager.getAuthToken === 'function')
                    ? manager.getAuthToken()
                    : (localStorage.getItem('access_token') || sessionStorage.getItem('access_token') || null);

                fetch(`/api/admin/users/${currentUserId}`, {
                    headers: Object.assign({ 'Content-Type': 'application/json' }, token ? { 'Authorization': `Bearer ${token}` } : {})
                })
                    .then(r => {
                        if (r.ok) return r.json();
                        if (r.status === 401) {
                            // Unauthorized - surface friendly error
                            if (manager && typeof manager.showError === 'function') manager.showError('Yêu cầu xác thực không hợp lệ. Vui lòng đăng nhập lại.');
                            return Promise.reject(new Error('Unauthorized'));
                        }
                        return Promise.reject(r);
                    })
                    .then(data => fillAndShowEditModal(data))
                    .catch((err) => {
                        console.warn('Fallback fetch for user failed', err);
                        // Final fallback: show message
                        if (manager && typeof manager.showError === 'function') manager.showError('Không tìm thấy thông tin người dùng');
                        else alert('Không tìm thấy thông tin người dùng');
                    });
            } catch (err) {
                console.warn('Error attempting fallback fetch for user', err);
                if (manager && typeof manager.showError === 'function') manager.showError('Không tìm thấy thông tin người dùng');
            }
            return;
        }

        fillAndShowEditModal(user);

        function fillAndShowEditModal(u) {
            const nameEl = document.getElementById('editUserName');
            const emailEl = document.getElementById('editUserEmail');
            const roleEl = document.getElementById('editUserRole');
            const statusEl = document.getElementById('editUserStatus');
            const createdEl = document.getElementById('editUserCreated');
            const lastLoginEl = document.getElementById('editUserLastLogin');
            const editModal = document.getElementById('editUserModal');

            if (nameEl) nameEl.value = u.fullname || u.name || '';
            if (emailEl) emailEl.value = u.email || '';
            if (roleEl) roleEl.value = u.role || 'user';
            if (statusEl) statusEl.value = (u.isActive === false || u.status === 'inactive') ? 'inactive' : 'active';
            if (createdEl) createdEl.value = u.createdAt || u.created_at || '';
            if (lastLoginEl) lastLoginEl.value = u.last_login || u.lastLogin || '';

            if (editModal) editModal.dataset.userId = currentUserId;

            // Hide detail modal if present, then show edit modal
            try {
                const detailInstance = bootstrap.Modal.getInstance(detailModal);
                if (detailInstance) detailInstance.hide();
            } catch (err) { /* ignore */ }

            setTimeout(() => {
                try {
                    const editInstance = new bootstrap.Modal(document.getElementById('editUserModal'));
                    editInstance.show();
                } catch (err) { console.warn('Failed showing edit modal', err); }
            }, 250);
        }
    } catch (err) {
        console.error('editUser wrapper error', err);
    }
}

async function saveUserChanges() {
    try {
        const editModal = document.getElementById('editUserModal');
        if (!editModal) return;
        const userId = editModal.dataset.userId;

        const name = document.getElementById('editUserName')?.value.trim() || '';
        const email = document.getElementById('editUserEmail')?.value.trim() || '';
        const role = document.getElementById('editUserRole')?.value || 'user';
        const status = document.getElementById('editUserStatus')?.value || 'active';

        // Basic validation
        if (!name || !email) {
            if (window.__adminUserManagement && typeof window.__adminUserManagement.showError === 'function') {
                window.__adminUserManagement.showError('Vui lòng điền đầy đủ thông tin bắt buộc!');
            } else alert('Vui lòng điền đầy đủ thông tin bắt buộc!');
            return;
        }

        // Try API update first
        const manager = window.__adminUserManagement;
        const token = manager ? manager.getAuthToken() : (localStorage.getItem('access_token') || '');

        const payload = { name, email, role, status };

        let updated = false;
        if (userId) {
            try {
                const res = await fetch(`/api/admin/users/${userId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': token ? `Bearer ${token}` : ''
                    },
                    body: JSON.stringify(payload)
                });

                if (res.ok) {
                    updated = true;
                    if (manager && typeof manager.showSuccess === 'function') manager.showSuccess('Cập nhật thông tin người dùng thành công!');
                }
            } catch (err) {
                console.warn('API update failed, will fallback to mock', err);
            }
        }

        // Fallback: update mock data if API not available
        if (!updated && manager && Array.isArray(manager.mockUsers)) {
            const idx = manager.mockUsers.findIndex(u => (u._id || u.id) == userId);
            if (idx !== -1) {
                const u = manager.mockUsers[idx];
                manager.mockUsers[idx] = {
                    ...u,
                    name: name,
                    fullname: name,
                    email: email,
                    role: role,
                    isActive: status === 'active',
                    status: status
                };
                if (manager && typeof manager.showSuccess === 'function') manager.showSuccess('Cập nhật (mock) thông tin người dùng thành công!');
                updated = true;
            }
        }

        // Close modal and refresh table
        try {
            const instance = bootstrap.Modal.getInstance(editModal);
            if (instance) instance.hide();
        } catch (err) { /* ignore */ }

        if (manager && typeof manager.loadUsers === 'function') manager.loadUsers();
        else location.reload();

    } catch (err) {
        console.error('saveUserChanges wrapper error', err);
        if (window.__adminUserManagement && typeof window.__adminUserManagement.showError === 'function') window.__adminUserManagement.showError('Có lỗi xảy ra khi cập nhật thông tin!');
    }
}
