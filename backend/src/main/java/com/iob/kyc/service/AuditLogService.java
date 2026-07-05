package com.iob.kyc.service;

import com.iob.kyc.model.AuditLog;
import com.iob.kyc.repository.AuditLogRepository;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;

@Service
public class AuditLogService {

    private final AuditLogRepository auditLogRepository;

    public AuditLogService(AuditLogRepository auditLogRepository) {
        this.auditLogRepository = auditLogRepository;
    }

    public void log(String employeeId, String employeeRole, String branchId,
                    String action, String entityType, String entityId,
                    String details, String ipAddress, String userAgent) {
        AuditLog entry = AuditLog.builder()
                .employeeId(employeeId)
                .employeeRole(employeeRole)
                .branchId(branchId)
                .action(action)
                .entityType(entityType)
                .entityId(entityId)
                .details(details)
                .ipAddress(ipAddress)
                .userAgent(userAgent)
                .createdAt(LocalDateTime.now())
                .build();
        auditLogRepository.save(entry);
    }

    public void log(String employeeId, String action, String entityType, String entityId, String details) {
        log(employeeId, null, null, action, entityType, entityId, details, null, null);
    }
}
