package com.iob.kyc.controller;

import com.iob.kyc.model.Employee;
import com.iob.kyc.repository.EmployeeRepository;
import com.iob.kyc.security.JwtTokenProvider;
import com.iob.kyc.service.AccountDetailsService;
import com.iob.kyc.service.AuditLogService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin/account-details")
@PreAuthorize("hasAnyRole('ADMIN', 'MANAGER', 'OFFICER')")
public class AccountDetailsController {

    private final AccountDetailsService accountDetailsService;
    private final JwtTokenProvider jwtTokenProvider;
    private final EmployeeRepository employeeRepository;
    private final AuditLogService auditLogService;

    public AccountDetailsController(AccountDetailsService accountDetailsService,
                                     JwtTokenProvider jwtTokenProvider,
                                     EmployeeRepository employeeRepository,
                                     AuditLogService auditLogService) {
        this.accountDetailsService = accountDetailsService;
        this.jwtTokenProvider = jwtTokenProvider;
        this.employeeRepository = employeeRepository;
        this.auditLogService = auditLogService;
    }

    @GetMapping("/search")
    public ResponseEntity<Map<String, Object>> searchAccounts(
            @RequestParam(required = false) String query,
            HttpServletRequest request) {

        Map<String, String> empInfo = extractEmployeeInfo(request);
        String role = empInfo.getOrDefault("employeeRole", "");
        String branchId = empInfo.getOrDefault("branchId", "");
        String employeeId = empInfo.getOrDefault("employeeId", "");

        List<Map<String, Object>> results = accountDetailsService.searchAccounts(query, role, branchId, employeeId);

        auditLogService.log(employeeId, role, branchId,
                "SEARCH_ACCOUNTS", "KYC_APPLICATION",
                query != null ? query : "ALL",
                "Searched accounts with query: " + (query != null ? query : "all"),
                getClientIp(request), request.getHeader("User-Agent"));

        Map<String, Object> response = new HashMap<>();
        response.put("success", true);
        response.put("data", results);
        response.put("count", results.size());
        return ResponseEntity.ok(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getAccountDetails(
            @PathVariable Long id,
            HttpServletRequest request) {

        Map<String, String> empInfo = extractEmployeeInfo(request);
        String role = empInfo.getOrDefault("employeeRole", "");
        String branchId = empInfo.getOrDefault("branchId", "");
        String employeeId = empInfo.getOrDefault("employeeId", "");

        Map<String, Object> details = accountDetailsService.getAccountDetails(id, role, branchId, employeeId);

        if (details == null) {
            auditLogService.log(employeeId, role, branchId,
                    "ACCESS_DENIED_ACCOUNT", "KYC_APPLICATION",
                    String.valueOf(id),
                    "Unauthorized access attempt to application " + id,
                    getClientIp(request), request.getHeader("User-Agent"));

            Map<String, Object> response = new HashMap<>();
            response.put("success", false);
            response.put("message", "Access denied or application not found");
            return ResponseEntity.status(403).body(response);
        }

        auditLogService.log(employeeId, role, branchId,
                "VIEW_ACCOUNT", "KYC_APPLICATION",
                String.valueOf(id),
                "Viewed customer account for application " + id,
                getClientIp(request), request.getHeader("User-Agent"));

        Map<String, Object> response = new HashMap<>();
        response.put("success", true);
        response.put("data", details);
        return ResponseEntity.ok(response);
    }

    private Map<String, String> extractEmployeeInfo(HttpServletRequest request) {
        Map<String, String> info = new HashMap<>();
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            try {
                String email = jwtTokenProvider.getUsernameFromToken(token);
                info.put("email", email);
                Employee emp = employeeRepository.findByEmail(email).orElse(null);
                if (emp != null) {
                    info.put("employeeId", emp.getEmployeeId());
                    info.put("employeeRole", emp.getRole().name());
                    info.put("branchId", emp.getBranchId() != null ? emp.getBranchId() : "");
                }
            } catch (Exception e) {
                // Token parsing failed
            }
        }
        return info;
    }

    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        if (ip != null && ip.contains(",")) {
            ip = ip.split(",")[0].trim();
        }
        return ip;
    }
}
