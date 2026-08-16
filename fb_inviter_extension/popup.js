document.addEventListener("DOMContentLoaded", async () => {
  const btnStart = document.getElementById("btn-start");
  const btnStop = document.getElementById("btn-stop");
  const btnDock = document.getElementById("btn-dock");
  const btnReset = document.getElementById("btn-reset-history");
  const btnTopup = document.getElementById("btn-topup");
  
  const statusText = document.getElementById("status-text");
  const invitedCount = document.getElementById("invited-count");
  const limitInput = document.getElementById("invite-limit");
  const tokenBalanceText = document.getElementById("token-balance");
  const topupCodeInput = document.getElementById("topup-code");
  const topupMsg = document.getElementById("topup-message");

  // Read saved state, limits, and wallet tokens from local storage
  // Default tokens to 50 on first install
  const storageData = await chrome.storage.local.get([
    "inviteCount", "isRunning", "inviteLimit", "statusMessage", "inviteHistory", "sessionHistory", "tokenBalance", "clientId"
  ]);
  
  invitedCount.textContent = storageData.inviteCount || 0;
  
  let currentTokens = storageData.tokenBalance !== undefined ? storageData.tokenBalance : 50;
  // Initialize storage if first time
  if (storageData.tokenBalance === undefined) {
    await chrome.storage.local.set({ tokenBalance: 50 });
  }
  tokenBalanceText.textContent = `${currentTokens} Tokens`;

  // Generate or read Client ID
  let clientId = storageData.clientId;
  if (!clientId) {
    const randPart = Math.random().toString(36).substring(2, 8).toUpperCase();
    clientId = `RCG-ID-${randPart}`;
    await chrome.storage.local.set({ clientId: clientId });
  }
  
  const clientIdDisplay = document.getElementById("client-id-display");
  if (clientIdDisplay) {
    clientIdDisplay.textContent = clientId;
  }

  // Validate approval status from cloud backend
  let isApproved = false;
  try {
    const res = await fetch(`https://racego-backend.onrender.com/api/clients/status?id=${clientId}`);
    const data = await res.json();
    if (data.success && data.approved) {
      isApproved = true;
    }
  } catch (e) {
    console.log("RaceGO Inviter: Backend offline, fallback to cached approval status.");
    const offlineData = await chrome.storage.local.get("isApproved");
    isApproved = !!offlineData.isApproved;
  }

  await chrome.storage.local.set({ isApproved: isApproved });

  if (!isApproved) {
    btnStart.disabled = true;
    btnStart.style.opacity = "0.5";
    btnStart.style.cursor = "not-allowed";
    btnStart.textContent = "รอการอนุมัติสิทธิ์ (Pending Approval)";
    statusText.textContent = "ล็อกอยู่ (Locked)";
    statusText.style.color = "var(--color-error)";
  }

  if (storageData.inviteLimit) limitInput.value = storageData.inviteLimit;
  
  if (storageData.isRunning) {
    showRunningState(storageData.statusMessage);
  } else {
    showStoppedState(storageData.statusMessage);
  }

  // Update history table initially
  updateHistoryStats(storageData.inviteHistory || [], storageData.sessionHistory || []);

  // Find active tab and check if it is Facebook
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url && tab.url.includes("facebook.com")) {
    try {
      // Inject content script immediately
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"]
      });
      
      // Request current status from the content script
      chrome.tabs.sendMessage(tab.id, { action: "status" }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response) {
          invitedCount.textContent = response.count;
          if (response.running) {
            showRunningState();
          } else {
            showStoppedState();
          }
        }
      });
    } catch (e) {
      console.log("Could not inject content script:", e);
    }
  } else {
    statusText.textContent = "กรุณาเปิดหน้า Facebook (Please open Facebook)";
    statusText.style.color = "var(--color-error)";
    btnStart.disabled = true;
  }

  // Start automation
  btnStart.addEventListener("click", async () => {
    // Check if token balance is positive
    const walletData = await chrome.storage.local.get({ tokenBalance: 100 });
    if ((walletData.tokenBalance || 0) <= 0) {
      alert("❌ เหรียญหมด! กรุณากรอกรหัสเพื่อเติมเหรียญก่อนใช้งาน (Out of Tokens!)");
      return;
    }

    const limit = parseInt(limitInput.value, 10) || 100;
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    // Save configurations and log new session run
    chrome.storage.local.get({ sessionHistory: [] }, async (data) => {
      const history = data.sessionHistory || [];
      history.push(Date.now());
      
      await chrome.storage.local.set({ 
        inviteLimit: limit,
        isRunning: true,
        statusMessage: "กำลังทำงาน... (Running)",
        sessionHistory: history,
        inviteCount: 0 // Reset current run count
      });
      invitedCount.textContent = 0;
    });
    
    if (tab) {
      showRunningState("กำลังทำงาน... (Running)");
      
      // Send message to start loop in content.js
      chrome.tabs.sendMessage(tab.id, { action: "start", limit: limit }, (response) => {
        if (chrome.runtime.lastError) {
          console.log("Error starting: content.js may not be loaded yet.");
        }
      });
    }
  });

  btnStop.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    // Save state
    await chrome.storage.local.set({ 
      isRunning: false,
      statusMessage: "หยุดชั่วคราว (Paused)"
    });
    
    if (tab) {
      showStoppedState("หยุดชั่วคราว (Paused)");
      
      // Send message to stop loop in content.js
      chrome.tabs.sendMessage(tab.id, { action: "stop" }, (response) => {
        if (chrome.runtime.lastError) {
          console.log("Error stopping: content.js may not be active.");
        }
      });
    }
  });

  // Topup Action
  btnTopup.addEventListener("click", async () => {
    const inputCode = topupCodeInput.value.trim().toUpperCase();
    if (!inputCode) {
      topupMsg.textContent = "กรุณากรอกรหัสเติมเงิน (Empty code)";
      topupMsg.style.color = "var(--color-error)";
      return;
    }
    
    topupMsg.textContent = "กำลังตรวจสอบรหัส... (Validating...)";
    topupMsg.style.color = "var(--text-secondary)";
    
    try {
      // Validate via Flask backend API
      const response = await fetch("https://racego-backend.onrender.com/api/tokens/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: inputCode })
      });
      
      const resData = await response.json();
      
      if (resData.success) {
        const addedTokens = resData.value;
        const wallet = await chrome.storage.local.get({ tokenBalance: 100 });
        let tokenBalance = wallet.tokenBalance !== undefined ? wallet.tokenBalance : 100;
        tokenBalance += addedTokens;
        
        await chrome.storage.local.set({ 
          tokenBalance, 
          activeCode: inputCode,
          statusMessage: `เติมสำเร็จ +${addedTokens} เหรียญ!`
        });
        
        tokenBalanceText.textContent = `${tokenBalance} Tokens`;
        topupCodeInput.value = "";
        topupMsg.textContent = `สำเร็จ! เติมแล้ว +${addedTokens} เหรียญ`;
        topupMsg.style.color = "var(--color-success)";
      } else {
        topupMsg.textContent = resData.error || "รหัสเติมเงินไม่ถูกต้อง";
        topupMsg.style.color = "var(--color-error)";
      }
    } catch (err) {
      console.log("Backend offline or unreachable, checking local validCodes...", err);
      // Offline fallback check
      const data = await chrome.storage.local.get({ validCodes: {}, tokenBalance: 100 });
      const validCodes = data.validCodes || {};
      let tokenBalance = data.tokenBalance !== undefined ? data.tokenBalance : 100;
      
      if (validCodes.hasOwnProperty(inputCode)) {
        const addedTokens = validCodes[inputCode];
        tokenBalance += addedTokens;
        delete validCodes[inputCode];
        
        await chrome.storage.local.set({ 
          tokenBalance, 
          validCodes,
          activeCode: inputCode,
          statusMessage: `เติมแบบออฟไลน์สำเร็จ +${addedTokens} เหรียญ!`
        });
        
        tokenBalanceText.textContent = `${tokenBalance} Tokens`;
        topupCodeInput.value = "";
        topupMsg.textContent = `สำเร็จ! เติมแบบออฟไลน์ +${addedTokens} เหรียญ`;
        topupMsg.style.color = "var(--color-success)";
      } else {
        topupMsg.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ และไม่พบรหัสออฟไลน์";
        topupMsg.style.color = "var(--color-error)";
      }
    }
  });


  // Dock Side Panel Button Click
  btnDock.addEventListener("click", () => {
    chrome.runtime.sendMessage({ action: "open_side_panel" }, (response) => {
      window.close();
    });
  });

  // Reset History Button Click
  btnReset.addEventListener("click", async () => {
    if (confirm("คุณแน่ใจหรือไม่ว่าต้องการล้างสถิติประวัติการส่งทั้งหมด? (Reset all history?)")) {
      await chrome.storage.local.set({
        inviteHistory: [],
        sessionHistory: [],
        inviteCount: 0
      });
      invitedCount.textContent = 0;
      updateHistoryStats([], []);
      alert("ล้างประวัติเรียบร้อยแล้ว!");
    }
  });

  // Periodically update UI from storage
  setInterval(async () => {
    const data = await chrome.storage.local.get(["inviteCount", "statusMessage", "inviteHistory", "sessionHistory", "tokenBalance"]);
    if (data.inviteCount !== undefined) {
      invitedCount.textContent = data.inviteCount;
    }
    if (data.tokenBalance !== undefined) {
      tokenBalanceText.textContent = `${data.tokenBalance} Tokens`;
    }
    if (data.statusMessage) {
      statusText.textContent = data.statusMessage;
      if (data.statusMessage.includes("พักสแปม")) {
        statusText.style.color = "var(--color-warning)";
      } else if (data.statusMessage.includes("กำลังทำงาน") || data.statusMessage.includes("Running")) {
        statusText.style.color = "var(--color-success)";
      } else if (data.statusMessage.includes("เสร็จสิ้น") || data.statusMessage.includes("สำเร็จ")) {
        statusText.style.color = "var(--color-success)";
        btnStart.style.display = "block";
        btnStop.style.display = "none";
      } else if (data.statusMessage.includes("เหรียญหมด")) {
        statusText.style.color = "var(--color-error)";
        btnStart.style.display = "block";
        btnStop.style.display = "none";
      }
    }
    updateHistoryStats(data.inviteHistory || [], data.sessionHistory || []);
  }, 1000);

  function updateHistoryStats(inviteHistory, sessionHistory) {
    const now = Date.now();
    const periods = {
      "24h": 24 * 3600 * 1000,
      "7d": 7 * 24 * 3600 * 1000,
      "15d": 15 * 24 * 3600 * 1000,
      "30d": 30 * 24 * 3600 * 1000
    };

    // Calculate runs and invites counts
    for (const [key, duration] of Object.entries(periods)) {
      const minTime = now - duration;
      
      const runsCount = sessionHistory.filter(ts => ts >= minTime).length;
      const invitesCount = inviteHistory.filter(ts => ts >= minTime).length;

      document.getElementById(`stat-run-${key}`).textContent = runsCount;
      document.getElementById(`stat-invite-${key}`).textContent = invitesCount;
    }
  }

  function showRunningState(customMsg) {
    btnStart.style.display = "none";
    btnStop.style.display = "block";
    statusText.textContent = customMsg || "กำลังทำงาน... (Running)";
    statusText.style.color = "var(--color-success)";
  }

  function showStoppedState(customMsg) {
    btnStart.style.display = "block";
    btnStop.style.display = "none";
    statusText.textContent = customMsg || "หยุดชั่วคราว (Paused)";
    statusText.style.color = "var(--color-warning)";
  }
});
