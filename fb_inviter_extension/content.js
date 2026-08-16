let inviteTimer = null; // Will store the setTimeout reference
let inviteCount = 0;
let runInvitesCount = 0; // Tracks consecutive invites in this session
let isCoolingDown = false;
let cooldownRemaining = 0;
let cooldownTimer = null;
let emptyScrollsCount = 0; // Tracks consecutive scroll checks with 0 buttons found

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "start") {
    // Reset limits on a fresh start
    runInvitesCount = 0;
    isCoolingDown = false;
    emptyScrollsCount = 0;
    if (cooldownTimer) clearInterval(cooldownTimer);
    
    // Read current count to resume correctly
    chrome.storage.local.get("inviteCount", (data) => {
      inviteCount = data.inviteCount || 0;
      inviteTimer = true; // Mark as running to allow start
      
      // 1. Auto click "All" / "ทั้งหมด" Tab on Facebook Reactions Modal
      clickAllTab();
      
      // 2. Begin schedule loop
      scheduleNextInvite(request.limit);
    });
    
    sendResponse({ status: "started" });
  } else if (request.action === "stop") {
    stopInviting();
    sendResponse({ status: "stopped" });
  } else if (request.action === "status") {
    sendResponse({ 
      running: inviteTimer !== null, 
      count: inviteCount,
      isCoolingDown: isCoolingDown,
      cooldownRemaining: cooldownRemaining
    });
  }
  return true;
});

function clickAllTab() {
  console.log("RaceGO Inviter: Searching for 'All' tab...");
  // Find tab triggers inside the FB reactions dialog
  const tabs = document.querySelectorAll('div[role="dialog"] div[role="tab"], div[role="dialog"] a[role="tab"], div[role="dialog"] span[role="tab"]');
  for (const tab of tabs) {
    const text = (tab.textContent || '').trim();
    if (text === "All" || text === "ทั้งหมด" || text.toLowerCase() === "all") {
      try {
        tab.click();
        console.log("RaceGO Inviter: Successfully clicked 'All' (ทั้งหมด) tab!");
      } catch (e) {
        console.error("RaceGO Inviter: Error clicking 'All' tab:", e);
      }
      break;
    }
  }
}

function findInviteButtons() {
  const buttons = [];
  const allElements = document.querySelectorAll('div[role="button"], button, span[role="button"]');
  
  for (const el of allElements) {
    const text = (el.textContent || '').trim();
    const ariaLabel = (el.getAttribute('aria-label') || '');
    
    const isInviteText = text === "Invite" || text === "เชิญ";
    const isInviteAria = ariaLabel.includes("Invite") || ariaLabel.includes("เชิญ");
    
    // Make sure it's not already invited (like "Invited" or "เชิญแล้ว")
    const isAlreadyInvited = text.includes("Invited") || text.includes("เชิญแล้ว") || text.includes("ส่งคำเชิญแล้ว");
    
    if ((isInviteText || isInviteAria) && !isAlreadyInvited) {
      buttons.push(el);
    }
  }
  return buttons;
}

function playSuccessBeep() {
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    osc.type = "sine";
    // Play a nice 2-second notification chime (C5 -> E5 -> G5 -> C6)
    osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); 
    osc.frequency.setValueAtTime(659.25, audioCtx.currentTime + 0.15); 
    osc.frequency.setValueAtTime(783.99, audioCtx.currentTime + 0.3); 
    osc.frequency.setValueAtTime(1046.50, audioCtx.currentTime + 0.45); 
    
    gain.gain.setValueAtTime(0.2, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 2.0); 
    
    osc.start();
    osc.stop(audioCtx.currentTime + 2.0);
    console.log("RaceGO Inviter: Played completion chime.");
  } catch (e) {
    console.log("Could not play notification sound:", e);
  }
}

function playErrorBeep() {
  try {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    
    osc.type = "sawtooth";
    // Low pitched error buzz
    osc.frequency.setValueAtTime(150.00, audioCtx.currentTime); 
    osc.frequency.setValueAtTime(120.00, audioCtx.currentTime + 0.25); 
    
    gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 1.0); 
    
    osc.start();
    osc.stop(audioCtx.currentTime + 1.0);
    console.log("RaceGO Inviter: Played error alarm.");
  } catch (e) {
    console.log("Could not play error sound:", e);
  }
}

function scheduleNextInvite(limitCount) {
  if (!inviteTimer) return;

  // Calculate random delay between 2 and 10 seconds
  const randomDelayMs = (Math.floor(Math.random() * (10 - 2 + 1)) + 2) * 1000;
  console.log(`RaceGO Inviter: Next invite scheduled in ${(randomDelayMs / 1000).toFixed(1)}s`);

  inviteTimer = setTimeout(async () => {
    // 1. Check if user reached cooldown
    if (isCoolingDown) {
      scheduleNextInvite(limitCount);
      return;
    }

    // 2. Check token balance first!
    const wallet = await chrome.storage.local.get({ tokenBalance: 100 });
    const currentTokens = wallet.tokenBalance !== undefined ? wallet.tokenBalance : 100;
    
    if (currentTokens <= 0) {
      console.log("RaceGO Inviter: Out of tokens!");
      chrome.storage.local.set({ statusMessage: "🪙 เหรียญหมด! กรุณาเติมเงิน (Out of Tokens)" });
      playErrorBeep();
      stopInviting();
      return;
    }

    // 3. Check total limit count
    if (inviteCount >= limitCount) {
      console.log(`RaceGO Inviter: Reached maximum limit of ${limitCount} invites.`);
      chrome.storage.local.set({ statusMessage: "เสร็จสิ้นตามลิมิต! (Limit Reached)" });
      playSuccessBeep();
      stopInviting();
      return;
    }

    // 4. Check for 20 invites pause cooldown rule
    if (runInvitesCount >= 20) {
      triggerCooldown(limitCount);
      return;
    }

    const buttons = findInviteButtons();
    
    if (buttons.length === 0) {
      // Auto scroll the reactions list modal dynamically
      let scrolled = false;
      let reachedBottom = true;
      const elements = document.querySelectorAll('div[role="dialog"] *');
      for (const el of elements) {
        if (el.scrollHeight > el.clientHeight) {
          const style = window.getComputedStyle(el);
          if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
            // Check if we reached the bottom of this scroll container
            const isAtBottom = Math.abs(el.scrollHeight - el.clientHeight - el.scrollTop) < 15;
            if (!isAtBottom) {
              el.scrollTop += 450;
              reachedBottom = false;
              scrolled = true;
            }
          }
        }
      }
      
      if (!scrolled) {
        window.scrollBy(0, 450);
        const isWindowAtBottom = (window.innerHeight + window.scrollY) >= document.body.offsetHeight - 15;
        if (!isWindowAtBottom) {
          reachedBottom = false;
        }
      }

      // Only increment retry counter if we have reached the absolute bottom of the scroll container
      if (reachedBottom) {
        emptyScrollsCount++;
        console.log(`RaceGO Inviter: Reached bottom. No buttons found. Retry #${emptyScrollsCount}/8`);
        
        if (emptyScrollsCount >= 8) {
          console.log("RaceGO Inviter: No buttons found after reaching bottom. Completed!");
          chrome.storage.local.set({ statusMessage: "เสร็จสิ้น! (No More Invites)" });
          playSuccessBeep();
          stopInviting();
          return;
        }
      } else {
        // Reset count because we are still successfully scrolling down to load new users
        emptyScrollsCount = 0;
        console.log("RaceGO Inviter: Still scrolling to load more users...");
      }

      scheduleNextInvite(limitCount);
      return;
    }
    
    // Found buttons, reset empty scrolls
    emptyScrollsCount = 0;
    
    // Click the first available invite button
    const targetButton = buttons[0];
    try {
      targetButton.scrollIntoView({ block: "center", behavior: "smooth" });
      targetButton.click();
      
      inviteCount++;
      runInvitesCount++;
      
      console.log(`RaceGO Inviter: Sent invite #${inviteCount} (Batch run count: ${runInvitesCount}/20)`);
      
      // Deduct 1 token and update counts & history in local storage
      chrome.storage.local.get({ inviteHistory: [] }, async (data) => {
        const history = data.inviteHistory || [];
        history.push(Date.now());
        
        await chrome.storage.local.set({ 
          inviteCount: inviteCount,
          inviteHistory: history,
          tokenBalance: Math.max(0, currentTokens - 1)
        });
      });
      
    } catch (e) {
      console.error("RaceGO Inviter: Click failed:", e);
    }

    // Schedule the next invite click recursion
    scheduleNextInvite(limitCount);
  }, randomDelayMs);
}

function triggerCooldown(limitCount) {
  isCoolingDown = true;
  runInvitesCount = 0;
  
  // Random time between 30 and 60 seconds
  cooldownRemaining = Math.floor(Math.random() * (60 - 30 + 1)) + 30;
  console.log(`RaceGO Inviter: Paused. Cooling down for ${cooldownRemaining}s to prevent spam block...`);
  
  cooldownTimer = setInterval(() => {
    cooldownRemaining--;
    if (cooldownRemaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
      isCoolingDown = false;
      console.log("RaceGO Inviter: Cooldown finished. Resuming invites.");
      chrome.storage.local.set({ statusMessage: "กำลังทำงาน... (Running)" });
      // Resume scheduling
      scheduleNextInvite(limitCount);
    } else {
      chrome.storage.local.set({ 
        statusMessage: `พักสแปมอีก ${cooldownRemaining} วิ (Pause ${cooldownRemaining}s)` 
      });
    }
  }, 1000);
}

function stopInviting() {
  if (inviteTimer) {
    clearTimeout(inviteTimer);
    inviteTimer = null;
  }
  if (cooldownTimer) {
    clearInterval(cooldownTimer);
    cooldownTimer = null;
  }
  isCoolingDown = false;
  runInvitesCount = 0;
  chrome.storage.local.set({ isRunning: false });
  console.log("RaceGO Inviter: Stopped operations.");
}

// Sync remaining token balance back to Flask backend every 1 minute
setInterval(async () => {
  const data = await chrome.storage.local.get(["activeCode", "tokenBalance"]);
  if (data.activeCode && data.tokenBalance !== undefined) {
    try {
      await fetch("http://localhost:8001/api/tokens/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: data.activeCode, balance: data.tokenBalance })
      });
      console.log(`RaceGO Inviter: Synced balance (${data.tokenBalance} Tokens) to backend.`);
    } catch (e) {
      console.log("RaceGO Inviter: Backend offline, sync postponed.", e);
    }
  }
}, 60000);
