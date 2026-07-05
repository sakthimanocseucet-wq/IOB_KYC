package com.iob.kyc.repository;

import com.iob.kyc.model.AuditLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.List;

public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

    List<AuditLog> findByEmployeeIdOrderByCreatedAtDesc(String employeeId);

    List<AuditLog> findByActionOrderByCreatedAtDesc(String action);

    @Query("SELECT a FROM AuditLog a WHERE a.createdAt >= :since ORDER BY a.createdAt DESC")
    List<AuditLog> findRecentLogs(@Param("since") LocalDateTime since);

    @Query("SELECT a FROM AuditLog a WHERE a.branchId = :branchId AND a.createdAt >= :since ORDER BY a.createdAt DESC")
    List<AuditLog> findByBranchAndSince(@Param("branchId") String branchId, @Param("since") LocalDateTime since);
}
