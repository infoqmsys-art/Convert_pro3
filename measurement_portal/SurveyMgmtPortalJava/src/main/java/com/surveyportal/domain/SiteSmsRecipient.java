package com.surveyportal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "site_sms_recipient")
public class SiteSmsRecipient {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "site_id", nullable = false)
  private Long siteId;

  @Column(name = "send_enabled", nullable = false)
  private Integer sendEnabled = 1;

  @Column(nullable = false)
  private String name;

  @Column(nullable = false)
  private String phone;

  @Column(name = "job_title")
  private String jobTitle;

  private String department;

  private String info;

  @Column(name = "sort_order", nullable = false)
  private Integer sortOrder = 0;

  @Column(name = "created_at")
  private String createdAt;

  public Long getId() {
    return id;
  }

  public void setId(Long id) {
    this.id = id;
  }

  public Long getSiteId() {
    return siteId;
  }

  public void setSiteId(Long siteId) {
    this.siteId = siteId;
  }

  public Integer getSendEnabled() {
    return sendEnabled;
  }

  public void setSendEnabled(Integer sendEnabled) {
    this.sendEnabled = sendEnabled;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public String getPhone() {
    return phone;
  }

  public void setPhone(String phone) {
    this.phone = phone;
  }

  public String getJobTitle() {
    return jobTitle;
  }

  public void setJobTitle(String jobTitle) {
    this.jobTitle = jobTitle;
  }

  public String getDepartment() {
    return department;
  }

  public void setDepartment(String department) {
    this.department = department;
  }

  public String getInfo() {
    return info;
  }

  public void setInfo(String info) {
    this.info = info;
  }

  public Integer getSortOrder() {
    return sortOrder;
  }

  public void setSortOrder(Integer sortOrder) {
    this.sortOrder = sortOrder;
  }

  public String getCreatedAt() {
    return createdAt;
  }

  public void setCreatedAt(String createdAt) {
    this.createdAt = createdAt;
  }
}
