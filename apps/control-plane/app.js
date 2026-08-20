const runButton=document.querySelector('#runBtn');const replayButton=document.querySelector('#replayBtn');
function flash(button,label){const original=button.textContent;button.textContent=label;button.disabled=true;setTimeout(()=>{button.textContent=original;button.disabled=false},1100)}
runButton?.addEventListener('click',()=>flash(runButton,'Queued'));replayButton?.addEventListener('click',()=>flash(replayButton,'Replay ready'));
document.querySelectorAll('nav a').forEach(link=>link.addEventListener('click',()=>{document.querySelectorAll('nav a').forEach(a=>a.classList.remove('active'));link.classList.add('active')}));
