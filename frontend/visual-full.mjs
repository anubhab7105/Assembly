import { chromium } from "playwright"
const BASE="http://localhost:3100"
const OUT="C:/Users/Arkap/AppData/Local/Temp/opencode/assembly_visual"
const history=[{id:"local-visual-1",question:"Should we move the primary database to a multi-region deployment now, or wait until traffic grows?",answer:"**Wait for now.** At the current scale, a single primary with read replicas is cheaper and simpler.\n\n- Read replicas cover the read-heavy path without cross-region write coordination.\n- The operational cost of multi-region failover is hard to justify below roughly 10x current traffic.\n- Revisit when latency targets or uptime requirements demand it.\n\n### What changes the answer\n\nA hard regional-uptime requirement or a latency SLO below 120 ms for a second continent would move the recommendation toward multi-region.",status:"completed",created_at:new Date().toISOString(),minutes:10,consensus:0.72,confidence:"Moderate",agentCount:5,providers:["gemini","groq","openrouter"],debateRounds:2,tokens:18450,elapsedSeconds:548,modelFamilies:["gemini","gpt-oss","gemma"],verification:{agents:5,families:3,rounds:2,disagreements_resolved:1,sources_verified:3},disagreements:[{id:"d1",agent_id:"sk-1",issue:"The cost estimate ignores cross-region egress.",resolved:true},{id:"d2",agent_id:"sk-2",issue:"No agent checked the real traffic curve.",resolved:false}],attachments:[]}]
const catalog={providers:[{id:"gemini",enabled:true,limits_ready:true,key_url:"https://aistudio.google.com/app/apikey",models:[{id:"a",family:"gemini",roles:["planner","synthesizer"],scope:"model"},{id:"b",family:"gemini",roles:["solver","researcher"],scope:"model"}]},{id:"groq",enabled:true,limits_ready:true,key_url:"https://console.groq.com/keys",models:[{id:"c",family:"gpt-oss",roles:["solver"],scope:"model"},{id:"d",family:"llama",roles:["critic"],scope:"model"}]},{id:"openrouter",enabled:true,limits_ready:true,key_url:"https://openrouter.ai/keys",models:[{id:"e",family:"gemma",roles:["solver","critic"],scope:"account"}]},{id:"mistral",enabled:true,limits_ready:false,limits_issue:"Free-tier limits are unverified.",key_url:"https://console.mistral.ai/api-keys/",models:[{id:"f",family:"mistral",roles:["solver"],scope:"model"}]}],families:["gemini","gpt-5","gemma","llama","mistral"],recommended_order:["gemini","groq","openrouter","mistral"],minimum_families:2}
async function seed(page){await page.evaluate(async({history})=>{await new Promise((res,rej)=>{const r=indexedDB.open("assembly",1);r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains("kv"))r.result.createObjectStore("kv")};r.onerror=()=>rej(r.error);r.onsuccess=()=>{const db=r.result;const tx=db.transaction("kv","readwrite");const s=tx.objectStore("kv");s.put(history,"history");s.put(JSON.stringify({version:2,acknowledged_at:new Date().toISOString()}),"setting:privacy_notice_ack");tx.oncomplete=()=>res();tx.onerror=()=>rej(tx.error)}})},{history})}
const browser=await chromium.launch({headless:true})
for (const [theme,width,height,label] of [["light",1440,1000,"desktop-light"],["dark",1440,1000,"desktop-dark"],["light",390,844,"mobile-light"],["dark",390,844,"mobile-dark"]]) {
 const ctx=await browser.newContext({viewport:{width,height},deviceScaleFactor:1})
 await ctx.addInitScript(({theme})=>{localStorage.setItem("assembly:theme",theme);localStorage.setItem("assembly:cookie-choice","dismissed")},{theme})
 await ctx.route("**/api/catalog",r=>r.fulfill({json:catalog}))
 await ctx.route("**/api/keys/test",r=>r.fulfill({json:{provider:"gemini",valid:true,rate_limited:false,message:"Connected."}}))
 const p=await ctx.newPage()
 await p.goto(BASE+"/",{waitUntil:"load"}); await seed(p)
 for(const [name,route] of [["executions","/executions?id=local-visual-1"],["history","/history"],["models","/models"],["settings","/settings"],["chat","/chat"]]){
  await p.goto(BASE+route,{waitUntil:"load"}); await p.waitForTimeout(900)
  await p.screenshot({path:`${OUT}/full-${label}-${name}.png`,fullPage:true})
 }
 await ctx.close()
}
await browser.close()
