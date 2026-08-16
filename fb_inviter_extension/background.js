// background.js
// Listening to open side panel requests from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "open_side_panel") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (tab) {
        chrome.sidePanel.open({ windowId: tab.windowId });
        sendResponse({ success: true });
      }
    });
    return true; // Keep message channel open for async response
  }
});
