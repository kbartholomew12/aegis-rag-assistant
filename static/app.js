
const q=document.getElementById("question"),askBtn=document.getElementById("askBtn"),statusEl=document.getElementById("status"),panel=document.getElementById("answerPanel"),answerText=document.getElementById("answerText"),actionBadge=document.getElementById("actionBadge"),modeBadge=document.getElementById("modeBadge"),riskText=document.getElementById("riskText"),reviewText=document.getElementById("reviewText"),sourcesEl=document.getElementById("sources"),sourcesSection=document.getElementById("sourcesSection"),noSources=document.getElementById("noSources"),toggleSources=document.getElementById("toggleSources"),charCount=document.getElementById("charCount");

document.querySelectorAll(".demo-question").forEach(btn=>btn.addEventListener("click",()=>{
  const spans=btn.querySelectorAll("span"),content=spans[spans.length-1],clone=content.cloneNode(true),label=clone.querySelector("strong");
  if(label)label.remove();q.value=clone.textContent.trim().replace(/\s+/g," ");updateCount();q.focus();
}));
function updateCount(){charCount.textContent=`${q.value.length} / 500`}
q.addEventListener("input",updateCount);
toggleSources.addEventListener("click",()=>{const hidden=sourcesEl.classList.toggle("hidden");toggleSources.textContent=hidden?"Show sources":"Hide sources"});

async function ask(){
  const question=q.value.trim();if(!question){q.focus();return}
  askBtn.disabled=true;panel.classList.add("hidden");statusEl.classList.remove("hidden");
  try{
    const resp=await fetch("/api/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question})});
    const data=await resp.json();
    if(!resp.ok){
      const msg=data.detail || data.error || "Unable to retrieve guidance.";
      throw new Error(Array.isArray(msg)?msg.map(x=>x.msg).join(" "):msg);
    }
    answerText.textContent=data.answer;actionBadge.textContent=data.action;riskText.textContent=data.risk;reviewText.textContent=data.human_review;
    const riskClass=String(data.risk||"").toLowerCase();actionBadge.className="action-badge";
    if(riskClass.includes("high"))actionBadge.classList.add("high");else if(riskClass.includes("elevated"))actionBadge.classList.add("elevated");else if(riskClass.includes("unknown"))actionBadge.classList.add("unknown");
    modeBadge.textContent=data.mode==="claude"?"RAG + Claude synthesis":data.mode==="coverage_guardrail"?"Coverage guardrail":"Retrieval demo mode";
    const sources=data.sources||[];sourcesEl.innerHTML="";
    if(!sources.length){sourcesSection.classList.add("hidden");noSources.classList.remove("hidden")}
    else{
      sourcesSection.classList.remove("hidden");noSources.classList.add("hidden");
      sources.forEach(src=>{
        const el=document.createElement("article");el.className=`source ${src.source_role==="primary"?"primary":""}`;
        const roleLabel=src.source_role==="primary"?"PRIMARY":"SUPPORTING",roleClass=src.source_role==="primary"?"":"supporting";
        el.innerHTML=`<div class="source-top"><div class="source-title">${escapeHtml(src.title)} · §${escapeHtml(src.section)}</div><div class="source-meta"><span class="role-badge ${roleClass}">${roleLabel}</span><span class="source-id">${escapeHtml(src.policy_id)}</span></div></div><p>${escapeHtml(src.text)}</p><div class="score">Semantic retrieval relevance: ${(src.score*100).toFixed(1)}%</div>`;
        sourcesEl.appendChild(el)
      })
    }
    panel.classList.remove("hidden");panel.scrollIntoView({behavior:"smooth",block:"start"})
  }catch(err){alert(err.message)}finally{statusEl.classList.add("hidden");askBtn.disabled=false}
}
function escapeHtml(str){return String(str).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]))}
askBtn.addEventListener("click",ask);q.addEventListener("keydown",e=>{if((e.ctrlKey||e.metaKey)&&e.key==="Enter")ask()});updateCount();
