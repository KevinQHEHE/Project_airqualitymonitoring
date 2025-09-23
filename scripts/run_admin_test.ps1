<#
Run a quick admin test against the local Flask server.
Purpose: log in, show access/refresh tokens, verify token with /api/auth/verify,
and call the admin users list at /api/admin/users/?page=1&page_size=20.

Usage (non-interactive):
  .\scripts\run_admin_test.ps1 -Email 'admin@example.com' -Password 'secret' -BaseUrl 'http://localhost:5000'

Or run without args to be prompted.
#>
param(
    [string]$Email = '',
    [string]$Password = '',
    [string]$BaseUrl = 'http://localhost:5000'
)

if (-not $Email) {
    $Email = Read-Host 'Email (e.g. admin@example.com)'
}
if (-not $Password) {
    # Prompt for password (plain text) for simplicity in dev environment
    $Password = Read-Host 'Password' -AsSecureString
    $BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
    $Password = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)
    [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($BSTR) | Out-Null
}

Write-Host "Using base URL: $BaseUrl"

try {
    $loginBody = @{ email = $Email; password = $Password } | ConvertTo-Json
    Write-Host 'Logging in...'
    $response = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method Post -Body $loginBody -ContentType 'application/json' -ErrorAction Stop
} catch {
    Write-Error "Login failed: $_"
    exit 2
}

$accessToken = $response.access_token
$refreshToken = $response.refresh_token

if (-not $accessToken) {
    Write-Error 'Login did not return access_token.'
    exit 3
}

Write-Host "Access token (truncated): $($accessToken.Substring(0,[Math]::Min(60,$accessToken.Length)))..."
if ($refreshToken) {
    $rt_display = $refreshToken.Substring(0,[Math]::Min(60,$refreshToken.Length)) + '...'
} else {
    $rt_display = '(none)'
}
Write-Host "Refresh token (truncated): $rt_display"

# Verify token
try {
    Write-Host 'Verifying token with /api/auth/verify...'
    $verify = Invoke-RestMethod -Uri "$BaseUrl/api/auth/verify" -Method Get -Headers @{ Authorization = "Bearer $accessToken"; Accept = 'application/json' } -ErrorAction Stop
    Write-Host "Verify response: $($verify | ConvertTo-Json -Depth 2)"
} catch {
    Write-Error "Token verify failed: $_"
    exit 4
}

# Call admin users endpoint (note trailing slash)
try {
    Write-Host 'Calling admin users endpoint...'
    $admin = Invoke-RestMethod -Uri "$BaseUrl/api/admin/users/?page=1&page_size=20" -Method Get -Headers @{ Authorization = "Bearer $accessToken"; Accept = 'application/json' } -ErrorAction Stop
    $count = 0
    if ($admin -and $admin.users) { $count = $admin.users.Count }
    Write-Host "Admin endpoint returned status OK; users count: $count"
    Write-Host "Sample response (truncated):"; $admin | Select-Object -Property pagination, @{Name='users_sample';Expression={$admin.users | Select-Object -First 5}} | ConvertTo-Json -Depth 3
} catch {
    Write-Error "Admin endpoint call failed: $_"
    exit 5
}

# Decode payload (inspect role and expiry)
try {
    $parts = $accessToken -split '\.'
    if ($parts.Length -ne 3) {
        Write-Error 'Access token is not a valid JWT (expected 3 segments)'
        exit 6
    }
    $payload = $parts[1]
    # compute padding length to make base64 length a multiple of 4
    $remainder = $payload.Length % 4
    $padlen = (4 - $remainder) % 4
    if ($padlen -gt 0) {
        # create a string consisting of '=' repeated padlen times
        $pad = New-Object System.String([char]'=', $padlen)
    } else {
        $pad = ''
    }
    $payloadPadded = $payload + $pad
    $jsonPayload = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($payloadPadded))
    Write-Host "Decoded token payload:"
    $jsonPayload | ConvertFrom-Json | ConvertTo-Json -Depth 4 | Write-Host
} catch {
    Write-Error "Failed to decode token payload: $_"
}

Write-Host 'Done.'
exit 0
