package com.surveyportal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "organization")
public class Organization {

  @Id private Long id;

  @Column(nullable = false, unique = true)
  private String name;

  private String code;
  private String memo;

  @Column(name = "created_at")
  private String createdAt;

  public Long getId() {
    return id;
  }

  public String getName() {
    return name;
  }
}
