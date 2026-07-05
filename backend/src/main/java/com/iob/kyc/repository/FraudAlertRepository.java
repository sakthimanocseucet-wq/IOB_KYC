package com.iob.kyc.repository;

import com.iob.kyc.model.FraudAlert;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface FraudAlertRepository extends JpaRepository<FraudAlert, Long> {
    List<FraudAlert> findByOrderByCreatedAtDesc();
    List<FraudAlert> findBySeverityOrderByCreatedAtDesc(FraudAlert.Severity severity);
    List<FraudAlert> findByAlertTypeOrderByCreatedAtDesc(FraudAlert.AlertType alertType);
    List<FraudAlert> findByResolvedOrderByCreatedAtDesc(boolean resolved);
    long countByResolved(boolean resolved);
}
