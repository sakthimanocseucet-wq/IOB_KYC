package com.iob.kyc.repository;

import com.iob.kyc.model.Branch;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface BranchRepository extends JpaRepository<Branch, Long> {
    Optional<Branch> findByBranchId(String branchId);
    Optional<Branch> findByIfscCode(String ifscCode);
    Optional<Branch> findByBranchNameContaining(String name);
    boolean existsByBranchId(String branchId);
    boolean existsByIfscCode(String ifscCode);
    List<Branch> findByIsActiveTrueOrderByBranchName();
}
