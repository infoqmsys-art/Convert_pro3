package com.surveyportal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "site")
public class Site {

  @Id private Long id;

  @Column(name = "organization_id", nullable = false)
  private Long organizationId;

  @Column(nullable = false)
  private String name;

  @Column(name = "site_code")
  private String siteCode;

  @Column(name = "install_date")
  private String installDate;

  @Column(name = "image_main")
  private String imageMain;

  @Column(name = "image_list")
  private String imageList;

  private String address;

  @Column(name = "site_program")
  private String siteProgram;

  private String memo;

  @Column(name = "created_at")
  private String createdAt;

  public Long getId() {
    return id;
  }

  public void setId(Long id) {
    this.id = id;
  }

  public Long getOrganizationId() {
    return organizationId;
  }

  public void setOrganizationId(Long organizationId) {
    this.organizationId = organizationId;
  }

  public String getName() {
    return name;
  }

  public void setName(String name) {
    this.name = name;
  }

  public String getSiteCode() {
    return siteCode;
  }

  public void setSiteCode(String siteCode) {
    this.siteCode = siteCode;
  }

  public String getInstallDate() {
    return installDate;
  }

  public void setInstallDate(String installDate) {
    this.installDate = installDate;
  }

  public String getImageMain() {
    return imageMain;
  }

  public void setImageMain(String imageMain) {
    this.imageMain = imageMain;
  }

  public String getImageList() {
    return imageList;
  }

  public void setImageList(String imageList) {
    this.imageList = imageList;
  }

  public String getAddress() {
    return address;
  }

  public void setAddress(String address) {
    this.address = address;
  }

  public String getSiteProgram() {
    return siteProgram;
  }

  public void setSiteProgram(String siteProgram) {
    this.siteProgram = siteProgram;
  }

  public String getMemo() {
    return memo;
  }

  public void setMemo(String memo) {
    this.memo = memo;
  }

  public String getCreatedAt() {
    return createdAt;
  }
}
