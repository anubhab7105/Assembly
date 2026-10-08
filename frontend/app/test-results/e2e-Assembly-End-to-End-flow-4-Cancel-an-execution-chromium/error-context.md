# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Assembly End-to-End flow >> 4. Cancel an execution
- Location: tests\e2e.spec.ts:110:7

# Error details

```
Test timeout of 30000ms exceeded.
```

# Page snapshot

```yaml
- generic [ref=f1e1]:
  - generic [ref=f1e2]:
    - complementary [ref=f1e3]:
      - generic [ref=f1e4]:
        - generic [ref=f1e5]:
          - link "Assembly" [ref=f1e6] [cursor=pointer]:
            - /url: /
          - button "New Investigation" [ref=f1e11]
        - generic [ref=f1e12]:
          - generic [ref=f1e13]: History
          - textbox "Search..." [ref=f1e23]
          - link "Will quantum computing achieve commercial advantage before 2030? 10/8/2026 completed" [ref=f1e24] [cursor=pointer]:
            - /url: /executions/exec-1
            - generic [ref=f1e27]:
              - paragraph [ref=f1e28]: Will quantum computing achieve commercial advantage before 2030?
              - generic [ref=f1e29]:
                - generic [ref=f1e30]: 10/8/2026
                - generic [ref=f1e31]: completed
            - button "Delete execution" [ref=f1e32]
          - link "Timeline for AGI? 10/7/2026 failed" [ref=f1e36] [cursor=pointer]:
            - /url: /executions/exec-2
            - generic [ref=f1e39]:
              - paragraph [ref=f1e40]: Timeline for AGI?
              - generic [ref=f1e41]:
                - generic [ref=f1e42]: 10/7/2026
                - generic [ref=f1e43]: failed
            - button "Delete execution" [ref=f1e44]
        - link "Settings" [ref=f1e49] [cursor=pointer]:
          - /url: /settings
    - main [ref=f1e54]:
      - main [ref=f1e56]:
        - generic [ref=f1e57]:
          - heading "Assembly" [level=1] [ref=f1e61]
          - paragraph [ref=f1e62]: Turn one question into a temporary team of AI agents that reason, debate, and verify to find the best answer.
        - generic [ref=f1e63]:
          - generic [ref=f1e67]:
            - paragraph [ref=f1e68]: Insufficient Model Diversity
            - paragraph [ref=f1e69]: Assembly requires at least 2 distinct model families to function.
          - button "Configure Keys" [ref=f1e70]
        - generic [ref=f1e71]:
          - generic [ref=f1e72]:
            - textbox "What do you want the team to research?" [active] [ref=f1e73]: Analyse the timeline and economic impacts of AGI given current scaling laws.
            - generic [ref=f1e74]:
              - generic [ref=f1e75]:
                - generic [ref=f1e76]: "Mode: Auto"
                - generic [ref=f1e77]:
                  - button "3m" [ref=f1e81]
                  - button "5m" [ref=f1e82]
                  - button "10m" [ref=f1e83]
                  - button "15m" [ref=f1e84]
                - generic "0 families configured" [ref=f1e85] [cursor=pointer]: 0 ready
              - button "Launch Team" [disabled]
          - generic [ref=f1e87]:
            - generic [ref=f1e88]: Shift + Enter for new line
            - generic [ref=f1e89]: Enter to send
        - generic [ref=f1e90]:
          - paragraph [ref=f1e96] [cursor=pointer]: Will quantum computing achieve commercial advantage before 2030?
          - paragraph [ref=f1e102] [cursor=pointer]: What are the most viable methods for replicating room-temperature superconductors?
          - paragraph [ref=f1e108] [cursor=pointer]: Analyse the timeline and economic impacts of AGI given current scaling laws.
          - paragraph [ref=f1e114] [cursor=pointer]: Which battery chemistry is most likely to replace Lithium-Ion in EVs by 2035?
  - generic "Notifications"
  - button "Open Next.js Dev Tools" [ref=f1e120] [cursor=pointer]
  - alert [ref=f1e124]
```