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

        // Bulk action buttons
        const bulkActivateBtn = document.getElementById('bulkActivate');
        const bulkDeactivateBtn = document.getElementById('bulkDeactivate');
        const bulkExportBtn = document.getElementById('bulkExport');

        if (bulkActivateBtn) {
            bulkActivateBtn.addEventListener('click', () => this.handleBulkAction('activate'));
        }
        if (bulkDeactivateBtn) {
            bulkDeactivateBtn.addEventListener('click', () => this.handleBulkAction('deactivate'));
        }
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

        // User detail modal triggers
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('view-user-btn')) {
                const userId = e.target.dataset.userId;
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
    }

    async loadUsers() {
        try {
            this.showLoading(true);
            
            // Use mock data instead of API call for frontend testing
            const searchTerm = document.getElementById('userSearch')?.value.toLowerCase() || '';
            const statusFilter = document.getElementById('statusFilter')?.value || '';
            const dateFrom = document.getElementById('dateFrom')?.value || '';
            const dateTo = document.getElementById('dateTo')?.value || '';
            
            // Filter mock data based on search and filters
            let filteredUsers = this.mockUsers;
            
            if (searchTerm) {
                filteredUsers = filteredUsers.filter(user => 
                    user.username.toLowerCase().includes(searchTerm) ||
                    user.email.toLowerCase().includes(searchTerm) ||
                    user.fullname.toLowerCase().includes(searchTerm)
                );
            }
            
            if (statusFilter === 'active') {
                filteredUsers = filteredUsers.filter(user => user.isActive);
            } else if (statusFilter === 'inactive') {
                filteredUsers = filteredUsers.filter(user => !user.isActive);
            }
            
            if (dateFrom && dateTo) {
                const fromDate = new Date(dateFrom);
                const toDate = new Date(dateTo);
                filteredUsers = filteredUsers.filter(user => {
                    const userDate = new Date(user.createdAt);
                    return userDate >= fromDate && userDate <= toDate;
                });
            }
            
            // Simulate pagination
            const startIndex = (this.currentPage - 1) * this.itemsPerPage;
            const endIndex = startIndex + this.itemsPerPage;
            const paginatedUsers = filteredUsers.slice(startIndex, endIndex);
            
            this.totalUsers = filteredUsers.length;
            this.renderUserTable(paginatedUsers);
            this.renderPagination(filteredUsers.length, Math.ceil(filteredUsers.length / this.itemsPerPage));
            this.updateBulkActionButtons();
            
        } catch (error) {
            console.error('Error loading users:', error);
            this.showError('Lỗi hiển thị dữ liệu');
        } finally {
            this.showLoading(false);
        }
    }

    renderUserTable(users) {
        const tbody = document.querySelector('#userTable tbody');
        if (!tbody) return;

        tbody.innerHTML = users.map(user => `
            <tr>
                <td>
                    <div class="form-check">
                        <input class="form-check-input user-checkbox" type="checkbox" 
                               value="${user._id}" ${this.selectedUsers.has(user._id) ? 'checked' : ''}>
                    </div>
                </td>
                <td>
                    <div class="d-flex align-items-center">
                        <div class="avatar-sm me-2">
                            <div class="avatar-title bg-primary rounded-circle text-white">
                                ${user.fullname.charAt(0).toUpperCase()}
                            </div>
                        </div>
                        <div>
                            <h6 class="mb-0">${user.fullname}</h6>
                            <small class="text-muted">${user.email}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <select class="form-select form-select-sm role-select" data-user-id="${user._id}">
                        <option value="user" ${user.role === 'user' ? 'selected' : ''}>User</option>
                        <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option>
                    </select>
                </td>
                <td>
                    <div class="form-check form-switch">
                        <input class="form-check-input status-toggle" type="checkbox" 
                               data-user-id="${user._id}" ${user.isActive ? 'checked' : ''}>
                        <label class="form-check-label">
                            ${user.isActive ? 'Hoạt động' : 'Không hoạt động'}
                        </label>
                    </div>
                </td>
                <td>
                    <span class="badge ${user.emailVerified ? 'bg-success' : 'bg-warning'}">
                        ${user.emailVerified ? 'Đã xác thực' : 'Chưa xác thực'}
                    </span>
                </td>
                <td>${new Date(user.createdAt).toLocaleDateString('vi-VN')}</td>
                <td>Chưa đăng nhập</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-user-btn" data-user-id="${user.id}">
                        <i class="fas fa-eye"></i> Chi tiết
                    </button>
                </td>
            </tr>
        `).join('');
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
            // Update mock data instead of API call
            const user = this.mockUsers.find(u => u._id === userId);
            if (user) {
                user.isActive = isActive;
                this.showSuccess(`Đã ${isActive ? 'kích hoạt' : 'vô hiệu hóa'} người dùng`);
                
                // Update the label text
                const checkbox = document.querySelector(`.status-toggle[data-user-id="${userId}"]`);
                if (checkbox) {
                    const label = checkbox.nextElementSibling;
                    if (label) {
                        label.textContent = isActive ? 'Hoạt động' : 'Không hoạt động';
                    }
                }
            } else {
                this.showError('Không tìm thấy người dùng');
                // Revert checkbox
                const checkbox = document.querySelector(`.status-toggle[data-user-id="${userId}"]`);
                if (checkbox) checkbox.checked = !isActive;
            }
        } catch (error) {
            console.error('Status toggle error:', error);
            this.showError('Lỗi thay đổi trạng thái');
        }
    }

    async changeUserRole(userId, newRole) {
        try {
            // Update mock data instead of API call
            const user = this.mockUsers.find(u => u._id === userId);
            if (user) {
                const oldRole = user.role;
                user.role = newRole;
                this.showSuccess(`Đã thay đổi vai trò từ ${oldRole} thành ${newRole}`);
            } else {
                this.showError('Không tìm thấy người dùng');
                // Revert select
                const select = document.querySelector(`.role-select[data-user-id="${userId}"]`);
                if (select) select.value = 'user';
            }
        } catch (error) {
            console.error('Role change error:', error);
            this.showError('Lỗi thay đổi vai trò');
        }
    }

    async showUserDetail(userId) {
        try {
            this.showLoading(true);
            
            // Find user from mock data instead of API call
            const user = this.mockUsers.find(u => u._id === userId);
            
            if (user) {
                this.renderUserDetailModal(user);
                const modal = new bootstrap.Modal(document.getElementById('userDetailModal'));
                modal.show();
            } else {
                this.showError('Không tìm thấy thông tin người dùng');
            }
        } catch (error) {
            console.error('Error loading user detail:', error);
            this.showError('Lỗi hiển thị thông tin người dùng');
        } finally {
            this.showLoading(false);
        }
    }

    renderUserDetailModal(user) {
        // Update modal header
        document.getElementById('userDetailName').textContent = user.fullname;
        document.getElementById('userDetailEmail').textContent = user.email;

        // Profile tab
        document.getElementById('userFullname').textContent = user.fullname;
        document.getElementById('userEmail').textContent = user.email;
        document.getElementById('userRole').textContent = user.role;
        document.getElementById('userStatus').innerHTML = user.isActive 
            ? '<span class="badge bg-success">Hoạt động</span>'
            : '<span class="badge bg-danger">Không hoạt động</span>';
        document.getElementById('userEmailVerified').innerHTML = user.emailVerified
            ? '<span class="badge bg-success">Đã xác thực</span>'
            : '<span class="badge bg-warning">Chưa xác thực</span>';
        document.getElementById('userCreatedAt').textContent = new Date(user.createdAt).toLocaleString('vi-VN');
        document.getElementById('userLastLogin').textContent = 'Chưa đăng nhập';

        // Locations tab
        this.renderUserLocations(user.favoriteLocations || []);

        // Alerts tab
        this.renderUserAlerts(user.alertSettings || {});
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

        if (!alertSettings || Object.keys(alertSettings).length === 0) {
            container.innerHTML = '<p class="text-muted">Người dùng chưa cài đặt cảnh báo nào.</p>';
            return;
        }

        container.innerHTML = `
            <div class="card mb-3">
                <div class="card-body">
                    <h6 class="card-title">Cài đặt cảnh báo</h6>
                    <div class="row">
                        <div class="col-md-6">
                            <p><strong>Email:</strong> 
                                <span class="badge ${alertSettings.enableEmail ? 'bg-success' : 'bg-secondary'}">
                                    ${alertSettings.enableEmail ? 'Bật' : 'Tắt'}
                                </span>
                            </p>
                        </div>
                        <div class="col-md-6">
                            <p><strong>Push Notification:</strong> 
                                <span class="badge ${alertSettings.enablePush ? 'bg-success' : 'bg-secondary'}">
                                    ${alertSettings.enablePush ? 'Bật' : 'Tắt'}
                                </span>
                            </p>
                        </div>
                    </div>
                    ${alertSettings.thresholds ? `
                        <div class="row">
                            <div class="col-md-6">
                                <p><strong>Ngưỡng PM2.5:</strong> ${alertSettings.thresholds.pm25} μg/m³</p>
                            </div>
                            <div class="col-md-6">
                                <p><strong>Ngưỡng PM10:</strong> ${alertSettings.thresholds.pm10} μg/m³</p>
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
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
    new AdminUserManagement();
});