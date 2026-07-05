package com.iob.kyc.service;

import com.iob.kyc.model.Employee;
import com.iob.kyc.model.User;
import com.iob.kyc.repository.EmployeeRepository;
import com.iob.kyc.repository.UserRepository;
import org.springframework.context.annotation.Primary;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@Primary
public class CustomUserDetailsService implements UserDetailsService {

    private final UserRepository userRepository;
    private final EmployeeRepository employeeRepository;

    public CustomUserDetailsService(UserRepository userRepository, EmployeeRepository employeeRepository) {
        this.userRepository = userRepository;
        this.employeeRepository = employeeRepository;
    }

    @Override
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        var empOpt = employeeRepository.findByEmail(email);
        if (empOpt.isPresent()) {
            Employee emp = empOpt.get();
            return new org.springframework.security.core.userdetails.User(
                    emp.getEmail(),
                    emp.getPasswordHash(),
                    emp.isActive(),
                    true, true, !emp.isLocked(),
                    List.of(new SimpleGrantedAuthority("ROLE_" + emp.getRole().name()))
            );
        }

        var userOpt = userRepository.findByEmail(email);
        if (userOpt.isPresent()) {
            User user = userOpt.get();
            return new org.springframework.security.core.userdetails.User(
                    user.getEmail(),
                    user.getPasswordHash(),
                    user.isActive(),
                    true, true, !user.isLocked(),
                    List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole()))
            );
        }

        throw new UsernameNotFoundException("User not found with email: " + email);
    }
}
