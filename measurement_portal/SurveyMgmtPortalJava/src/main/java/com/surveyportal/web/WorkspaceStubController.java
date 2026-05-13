package com.surveyportal.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

/** Java 이행 전 단계에서는 워크스페이스 본 기능은 미구현입니다. */
@Controller
public class WorkspaceStubController {

  @GetMapping("/site/{siteId}/workspace")
  public String workspaceStub(@PathVariable long siteId, Model model) {
    model.addAttribute("siteId", siteId);
    return "workspace-stub";
  }
}
