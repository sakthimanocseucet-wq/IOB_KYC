package com.iob.kyc.repository;

import com.iob.kyc.model.Employee;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface EmployeeRepository extends JpaRepository<Employee, Long> {

    Optional<Employee> findByEmail(String email);

    Optional<Employee> findByEmployeeId(String employeeId);

    boolean existsByEmail(String email);

    boolean existsByEmployeeId(String employeeId);

    @Query("SELECT e FROM Employee e WHERE REPLACE(REPLACE(e.phone, '+', ''), ' ', '') = REPLACE(REPLACE(:phone, '+', ''), ' ', '')")
    Optional<Employee> findByPhone(@Param("phone") String phone);
}
