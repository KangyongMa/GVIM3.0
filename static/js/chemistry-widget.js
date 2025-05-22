/**
 * Optimized Chemical Purchasing Assistant Widget
 * Professional Edition - Enhanced chemical procurement experience
 * Now with Authentication Awareness
 */

document.addEventListener('DOMContentLoaded', function() {
  initChemistryWidget();
});

// Global variable to store login status for the widget
let isUserLoggedInWidget = false;
let currentWidgetUser = null;

async function checkWidgetUserLoginStatus() {
  try {
    const response = await fetch('/get_current_user'); // API endpoint from app.py
    if (response.ok) {
      const userData = await response.json();
      if (userData.username) {
        isUserLoggedInWidget = true;
        currentWidgetUser = userData.username;
        console.log('Chemistry Widget: User is logged in as', currentWidgetUser);
        // Enable purchase button if it was previously disabled due to auth
        const startBtn = document.getElementById('start-purchase');
        if (startBtn && startBtn.disabled && startBtn.dataset.authDisabled) {
            startBtn.disabled = false;
            startBtn.removeAttribute('data-auth-disabled');
            const authMessage = document.getElementById('widget-auth-message');
            if (authMessage) authMessage.style.display = 'none';
        }
      } else {
        isUserLoggedInWidget = false;
        currentWidgetUser = null;
        console.log('Chemistry Widget: User is not logged in.');
        // Disable purchase button
        const startBtn = document.getElementById('start-purchase');
        if (startBtn) {
            startBtn.disabled = true;
            startBtn.dataset.authDisabled = 'true'; // Mark as disabled due to auth
        }
        const authMessage = document.getElementById('widget-auth-message');
        if (authMessage) {
            authMessage.textContent = 'Please log in to use the purchasing assistant.';
            authMessage.style.display = 'block';
        }
      }
    } else {
      isUserLoggedInWidget = false;
      currentWidgetUser = null;
      console.warn('Chemistry Widget: Failed to get current user status from server.');
      // Potentially disable functionality here too
        const startBtn = document.getElementById('start-purchase');
        if (startBtn) {
            startBtn.disabled = true;
            startBtn.dataset.authDisabled = 'true';
        }
        const authMessage = document.getElementById('widget-auth-message');
        if (authMessage) {
            authMessage.textContent = 'Could not verify login status. Purchasing disabled.';
            authMessage.style.display = 'block';
        }
    }
  } catch (error) {
    isUserLoggedInWidget = false;
    currentWidgetUser = null;
    console.error("Chemistry Widget: Error checking login status:", error);
    // Potentially disable functionality here too
    const startBtn = document.getElementById('start-purchase');
    if (startBtn) {
        startBtn.disabled = true;
        startBtn.dataset.authDisabled = 'true';
    }
    const authMessage = document.getElementById('widget-auth-message');
    if (authMessage) {
        authMessage.textContent = 'Error verifying login. Purchasing disabled.';
        authMessage.style.display = 'block';
    }
  }
}


function initChemistryWidget() {
  console.log("Initializing Optimized Chemical Purchasing Assistant");
  
  // Inject Widget HTML
  injectWidgetHTML();
  
  // Setup functionality - add delay to ensure DOM is fully loaded
  setTimeout(async () => { // Make this async to await login status
    await checkWidgetUserLoginStatus(); // Check login status first
    setupWidgetFunctionality();
    
    // Add debug info, confirm trigger area is correctly set
    const triggerArea = document.querySelector('.widget-trigger-area');
    if (triggerArea) {
      console.log("Trigger area set, width:", getComputedStyle(triggerArea).width);
    } else {
      console.error("Trigger area element not found!");
    }
  }, 100);
}

function injectWidgetHTML() {
  // Create widget HTML structure
  const widgetHTML = `
    <div id="chemistry-widget">
      <div class="widget-handle">
        <span>⚗️</span>
      </div>
      <div class="widget-content">
        <div class="widget-header">
          <div class="widget-title">
            <span>⚗️</span>
            <span>Chemical Purchasing Assistant</span>
          </div>
          <button class="widget-close">×</button>
        </div>
        <div class="widget-body">
          <div id="widget-auth-message" style="color: #f87171; font-size: 0.8rem; margin-bottom: 10px; text-align: center; display: none;">
            Please log in to use the purchasing assistant.
          </div>
          <div class="widget-section">
            <label for="supplier-select"><i class="fas fa-building"></i> Select Supplier</label>
            <select id="supplier-select">
              <option value="sigma">Sigma-Aldrich</option>
              <option value="fisher">Fisher Scientific</option>
              <option value="vwr">VWR International</option>
              <option value="alfa">Alfa Aesar</option>
              <option value="acros">Acros Organics</option>
              <option value="tci">TCI Chemicals</option>
              <option value="jt">J.T.Baker</option>
              <option value="aladdin">Aladdin</option>
              <option value="macklin">Macklin</option>
              <option value="bideph">Bide Pharmatech</option>
            </select>
          </div>
          <div class="widget-section">
            <label for="chemical-list"><i class="fas fa-flask"></i> Chemical List</label>
            <textarea id="chemical-list" placeholder="Enter one chemical per line..."></textarea>
            <div class="example-tip">
              <i class="fas fa-lightbulb"></i>
              <div>
                <div>Example Format:</div>
                <div>500g Sodium Chloride (NaCl)</div>
                <div>1L Methanol (CH<sub>3</sub>OH)</div>
                <div>100g Sodium Hydroxide (NaOH)</div>
              </div>
            </div>
            <div class="chemical-formatter">
              <button class="formula-btn" onclick="insertChemical('NaCl')">NaCl</button>
              <button class="formula-btn" onclick="insertChemical('CH₃OH')">CH₃OH</button>
              <button class="formula-btn" onclick="insertChemical('H₂SO₄')">H₂SO₄</button>
              <button class="formula-btn" onclick="insertChemical('NaOH')">NaOH</button>
              <button class="formula-btn" onclick="insertChemical('HCl')">HCl</button>
              <button class="formula-btn" onclick="insertChemical('KMnO₄')">KMnO₄</button>
            </div>
          </div>
          
          <div class="progress-area" style="display: none;"> <div class="progress-header">
              <div class="progress-title">
                <i class="fas fa-spinner fa-spin"></i> 
                <span>Processing Order</span>
              </div>
              <div class="progress-percentage">5%</div>
            </div>
            <div class="progress-text">Preparing...</div>
            <div class="progress-bar-container">
              <div class="progress-bar"></div>
            </div>
            <div class="progress-stats">
              <span class="progress-step">Step 1/4</span>
              <span class="progress-eta">Est. time remaining: 30s</span>
            </div>
          </div>
          
          <button id="start-purchase" class="widget-button">
            <i class="fas fa-shopping-cart"></i> Start Purchase
          </button>
        </div>
      </div>
    </div>
    <div class="widget-trigger-area"></div>
  `;
  
  // Inject widget HTML into the body
  const widgetContainer = document.createElement('div');
  widgetContainer.innerHTML = widgetHTML;
  document.body.appendChild(widgetContainer);
  
  // Ensure FontAwesome is available
  ensureFontAwesome();
}

function ensureFontAwesome() {
  // Check if FontAwesome is already loaded
  const fontAwesomeLoaded = Array.from(document.querySelectorAll('link')).some(link => 
    link.href.includes('font-awesome') || link.href.includes('fontawesome')
  );
  
  if (!fontAwesomeLoaded) {
    const fontAwesomeLink = document.createElement('link');
    fontAwesomeLink.rel = 'stylesheet';
    fontAwesomeLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'; // Using a common CDN
    document.head.appendChild(fontAwesomeLink);
    console.log("FontAwesome icons loaded for widget.");
  }
}

// Insert chemical formula
window.insertChemical = function(formula) {
  const textarea = document.getElementById('chemical-list');
  if (!textarea) return; // Guard clause
  const cursorPos = textarea.selectionStart;
  const textBefore = textarea.value.substring(0, cursorPos);
  const textAfter = textarea.value.substring(textarea.selectionEnd);
  
  // Replace numbers with Unicode subscript characters
  const formattedFormula = formula.replace(/(\d+)/g, (match) => {
    return Array.from(match).map(digit => {
      const subscripts = ['₀', '₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈', '₉'];
      return subscripts[parseInt(digit)];
    }).join('');
  });
  
  textarea.value = textBefore + formattedFormula + textAfter;
  textarea.focus();
  textarea.selectionStart = cursorPos + formattedFormula.length;
  textarea.selectionEnd = textarea.selectionStart;
};

function setupWidgetFunctionality() {
  console.log("Setting up widget functionality");
  
  // Get widget elements
  const widget = document.getElementById('chemistry-widget');
  if (!widget) {
      console.error("Chemistry widget main element not found!");
      return;
  }
  const handle = widget.querySelector('.widget-handle');
  const closeBtn = widget.querySelector('.widget-close');
  const startBtn = document.getElementById('start-purchase');
  const progressArea = widget.querySelector('.progress-area');
  const progressBar = widget.querySelector('.progress-bar');
  const progressText = widget.querySelector('.progress-text');
  const progressPercentage = widget.querySelector('.progress-percentage');
  const progressStep = widget.querySelector('.progress-step');
  const progressEta = widget.querySelector('.progress-eta');
  const triggerArea = document.querySelector('.widget-trigger-area');
  const authMessageEl = document.getElementById('widget-auth-message');


  if (!handle || !closeBtn || !startBtn || !progressArea || !progressBar || !progressText || !progressPercentage || !progressStep || !progressEta || !triggerArea || !authMessageEl) {
      console.error("One or more widget sub-elements not found. Functionality might be impaired.");
  }
  
  console.log("Trigger area element:", triggerArea);
  
  // State tracking
  let isOpen = false;
  let isMouseOverWidget = false;
  let isBusy = false;
  let autoCloseTimer = null;
  let openWidgetTimer = null;
  
  // Open widget function - Modified: reduce delay
  function openWidget() {
    if (!isOpen && !isBusy) {
      // Reduce delay
      clearTimeout(openWidgetTimer);
      openWidgetTimer = setTimeout(() => {
        widget.classList.add('open');
        isOpen = true;
        console.log("Widget opened");
      }, 50); // Reduced from 400ms to 50ms for quicker response
    }
  }
  
  // Close widget function
  function closeWidget() {
    if (isOpen && !isBusy) {
      widget.classList.remove('open');
      isOpen = false;
      console.log("Widget closed");
    }
  }
  
  // Mouse enters trigger area - Modified: reduce hover time
  if (triggerArea) {
    triggerArea.addEventListener('mouseenter', function() {
      console.log("Mouse entered trigger area");
      clearTimeout(openWidgetTimer);
      openWidgetTimer = setTimeout(() => {
        if (!isOpen) {
          openWidget();
        }
      }, 50); // Reduced from 250ms to 50ms for quicker response
    });
    
    // Add additional debug event
    triggerArea.addEventListener('mouseover', function() {
      // console.log("Mouse hovering over trigger area"); // Can be noisy
    });
    
    // Mouse leaves trigger area
    triggerArea.addEventListener('mouseleave', function(e) {
      clearTimeout(openWidgetTimer); // Cancel open timer
      if (!isMouseOverWidget) { // Only close if mouse is not moving onto the widget
        autoCloseTimer = setTimeout(() => { // Add delay to avoid closing if mouse is moving into widget
          if (!isMouseOverWidget && !isBusy) {
            closeWidget();
          }
        }, 300); // Moderate delay to allow moving into the widget
      }
    });
  }
  
  // Mouse enters widget
  widget.addEventListener('mouseenter', function() {
    isMouseOverWidget = true;
    if (autoCloseTimer) { // Clear auto-close timer
      clearTimeout(autoCloseTimer);
      autoCloseTimer = null;
    }
  });
  
  // Mouse leaves widget
  widget.addEventListener('mouseleave', function() {
    isMouseOverWidget = false;
    if (!isBusy) { // Set delayed close
      autoCloseTimer = setTimeout(closeWidget, 800); // Moderate delay, not too fast, not too slow
    }
  });
  
  // Click handle
  if (handle) {
    handle.addEventListener('click', function() {
      if (isOpen) {
        closeWidget();
      } else {
        clearTimeout(openWidgetTimer); // Open directly, no delay
        widget.classList.add('open');
        isOpen = true;
        console.log("Widget opened via click");
      }
    });
  }
  
  // Click close button
  if (closeBtn) {
    closeBtn.addEventListener('click', closeWidget);
  }
  
  // Purchase functionality
  if (startBtn) {
    startBtn.addEventListener('click', async function() { // Make async for auth check
      await checkWidgetUserLoginStatus(); // Re-check auth status on click

      if (!isUserLoggedInWidget) {
        showNotification('Please log in to start a purchase.', 'error');
        if (authMessageEl) { // Ensure message element exists
            authMessageEl.textContent = 'Please log in to use the purchasing assistant.';
            authMessageEl.style.display = 'block';
        }
        // Optionally, briefly open the widget if it's closed to show the message
        if (!isOpen) openWidget();
        return;
      }
      if (authMessageEl) authMessageEl.style.display = 'none'; // Hide auth message if logged in


      const supplierSelect = document.getElementById('supplier-select'); // Renamed for clarity
      const supplierName = supplierSelect.options[supplierSelect.selectedIndex].text;
      const chemicalListValue = document.getElementById('chemical-list').value.trim(); // Renamed
      
      if (!chemicalListValue) {
        showNotification('Please enter the chemical list!', 'error');
        return;
      }
      
      // Show progress area
      if(progressArea) progressArea.style.display = 'block';
      updateProgress('Preparing purchase process...', 5, 1, 4);
      
      // Disable button and set busy state
      startBtn.disabled = true;
      isBusy = true;
      
      // Parse chemical list - enhanced format handling
      const chemicals = parseChemicalList(chemicalListValue);
      
      console.log("Starting purchase process:", supplierName, chemicals);
      
      // Start simulated purchase process
      simulatePurchase(supplierSelect.value, supplierName, chemicals);
    });
  }
  
  // Parse chemical list, supports multiple formats
  function parseChemicalList(text) {
    return text.split('\n')
      .map(line => {
        line = line.trim();
        if (line.length === 0) return null;
        
        // Try to match common chemical formats: Quantity Name (Formula)
        const formats = [
          /^(\d+[A-Za-z]+)\s+(.+?)(?:\s*\(([^)]+)\))?$/,  // e.g., "500g Sodium Chloride (NaCl)"
          /^(.+?)(?:\s*\(([^)]+)\))?$/                     // e.g., "Sodium Chloride (NaCl)" or "Sodium Chloride"
        ];
        
        for (const format of formats) {
          const match = line.match(format);
          if (match) {
            // Return different structures based on matched pattern
            if (match.length >= 4 && match[3]) {  // Has formula
              return {
                text: line,
                quantity: match[1],
                name: match[2],
                formula: match[3]
              };
            } else if (match.length >= 3 && match[2]) {  // No quantity, has formula
              return {
                text: line,
                name: match[1],
                formula: match[2]
              };
            } else {  // Only name
              return {
                text: line,
                name: match[1]
              };
            }
          }
        }
        
        // If no match with above formats, return original text
        return { text: line };
      })
      .filter(item => item !== null);
  }
  
  // Update progress display
  function updateProgress(message, percentage, currentStepVal, totalStepsVal, eta = "Calculating...") {
    if(progressText) progressText.textContent = message;
    if(progressBar) progressBar.style.width = `${percentage}%`;
    if(progressPercentage) progressPercentage.textContent = `${percentage}%`;
    if(progressStep) progressStep.textContent = `Step ${currentStepVal}/${totalStepsVal}`;
    if(progressEta) progressEta.textContent = `Est. time remaining: ${eta}`;
    console.log(`Purchase progress: ${percentage}% - ${message}`);
  }
  
  // Simulate purchase process
  function simulatePurchase(supplierCode, supplierName, chemicals) {
    // const totalItems = chemicals.length; // Not directly used in this version of simulation steps
    const totalSteps = 4; // Login + Cart + Checkout + Confirm
    let currentStepVal = 1;
    let startTime = Date.now();
    
    // Update estimated time remaining function
    function updateEta(completedPercentage) {
        const elapsedMs = Date.now() - startTime;
        if (completedPercentage <= 0) return "Calculating...";
        
        const totalEstimatedMs = (elapsedMs / completedPercentage) * 100;
        const remainingMs = totalEstimatedMs - elapsedMs;
        
        if (remainingMs < 1000) return "Almost done";
        if (remainingMs < 60000) return `${Math.ceil(remainingMs / 1000)}s`;
        return `${Math.ceil(remainingMs / 60000)}min`;
    }
    
    // Update progress display - Connecting
    updateProgress(`Connecting to ${supplierName}...`, 5, 1, totalSteps);
    
    // Prepare request data
    const chemicalItems = chemicals.map(item => item.text);
    
    // Send actual API request
    fetch('/chemical_purchase', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            supplier: supplierCode,
            items: chemicalItems
        })
    })
    .then(response => {
        if (!response.ok) {
            // Try to parse error from backend if available
            return response.json().then(errData => {
                throw new Error(errData.error || `HTTP error! status: ${response.status}`);
            }).catch(() => { // Fallback if error parsing fails
                throw new Error(`HTTP error! status: ${response.status}`);
            });
        }
        // Update progress display - Logging in
        updateProgress(`Logging into ${supplierName} system...`, 15, 1, totalSteps, updateEta(15));
        return response.json();
    })
    .then(data => {
        // Handle cart step
        currentStepVal = 2;
        updateProgress(`Preparing to add items to cart...`, 25, 2, totalSteps, updateEta(25));
        
        // Simulate UI progress update, but use real data
        setTimeout(() => {
            const itemNames = data.items && Array.isArray(data.items) ? 
                data.items.map(item => typeof item === 'string' ? item : (item.name || 'Unknown Item')) : 
                chemicalItems;
            
            // Display adding items progress one by one
            let itemIndex = 0;
            function processNextItem() {
                if (itemIndex < itemNames.length) {
                    const progress = 25 + ((itemIndex + 1) / itemNames.length * 40); // Spread 40% for item addition
                    updateProgress(
                        `Adding ${itemNames[itemIndex]} to cart...`, 
                        Math.min(progress, 65), // Cap at 65% for this stage
                        2, 
                        totalSteps, 
                        updateEta(Math.min(progress, 65))
                    );
                    itemIndex++;
                    setTimeout(processNextItem, 600); // Simulate delay for each item
                } else {
                    // Enter checkout step
                    currentStepVal = 3;
                    updateProgress(`Verifying cart items...`, 70, 3, totalSteps, updateEta(70));
                    
                    setTimeout(() => {
                        updateProgress(`Processing payment information...`, 80, 3, totalSteps, updateEta(80));
                        
                        setTimeout(() => {
                            // Final confirmation step
                            currentStepVal = 4;
                            updateProgress(`Confirming order details...`, 90, 4, totalSteps, updateEta(90));
                            
                            setTimeout(() => {
                                updateProgress(`Order Complete!`, 100, 4, totalSteps, "Completed");
                                
                                // Display order summary using actual data returned by API
                                setTimeout(() => {
                                    displayOrderSummary(supplierCode, supplierName, data);
                                    
                                    // Reset UI state
                                    setTimeout(() => {
                                        if(progressArea) progressArea.style.display = 'none';
                                        if(startBtn) startBtn.disabled = false;
                                        isBusy = false;
                                    }, 1000); // Delay before hiding progress
                                }, 1000); // Delay before showing summary
                            }, 800); // Delay for confirming order
                        }, 1000); // Delay for processing payment
                    }, 1200); // Delay for verifying cart
                }
            }
            
            processNextItem();
        }, 1000); // Initial delay before starting item processing
    })
    .catch(error => {
        console.error('Error in chemical purchase:', error);
        showNotification(`Error during purchase: ${error.message}`, 'error');
        
        // Reset UI state
        if(progressArea) progressArea.style.display = 'none';
        if(startBtn) {
            startBtn.disabled = false; // Re-enable button on error
            // If it was disabled due to auth, keep it disabled
            if (startBtn.dataset.authDisabled === 'true' && !isUserLoggedInWidget) {
                 startBtn.disabled = true;
            }
        }
        isBusy = false;
    });
}
  
  // Display order summary
  function displayOrderSummary(supplierCode, supplierName, orderData) {
    // Use order data returned by API
    const orderId = orderData.order_id || generateOrderId(supplierCode); // Fallback if not provided
    const items = orderData.items || []; // Ensure items is an array
    const totalPrice = orderData.total_price || 0;
    const estimatedDelivery = orderData.estimated_delivery || getEstimatedDeliveryDays(supplierCode) + ' business days';
    
    const orderDate = new Date();
    
    const summaryHTML = `
      <div class="order-summary">
        <div class="order-summary-header">
          <div class="order-summary-icon">📋</div>
          <h3>Chemical Order Summary</h3>
        </div>
        
        <p><strong>Supplier:</strong> ${supplierName}</p>
        <p><strong>Order Date:</strong> ${formatDate(orderDate)}</p>
        <p><strong>Items Ordered:</strong></p>
        <ul>
          ${items.map(item => {
              // Adjust display based on data structure returned by API
              if (typeof item === 'string') {
                  return `<li>${item}</li>`;
              } else if (item && typeof item === 'object' && item.name) { // Check if item is an object with a name
                  const displayName = item.quantity ? `${item.quantity} ${item.name}` : item.name;
                  const displayCAS = item.cas ? ` (CAS: ${item.cas})` : '';
                  const displayPrice = typeof item.price === 'number' ? ` - ¥${item.price.toFixed(2)}` : '';
                  return `<li>${displayName}${displayCAS}${displayPrice}</li>`;
              }
              return `<li>Invalid item data</li>`; // Fallback for unexpected item format
          }).join('')}
        </ul>
        <p><strong>Estimated Delivery:</strong> ${estimatedDelivery}</p>
        <p><strong>Order Status:</strong> <span style="color: #059669; font-weight: 500;">✅ Successfully Placed</span></p>
        
        <div class="order-summary-footer">
          <div><strong>Total Price:</strong> ¥${typeof totalPrice === 'number' ? totalPrice.toFixed(2) : totalPrice}</div>
          <div class="order-id">Order ID: ${orderId}</div>
        </div>
      </div>
    `;
    
    // Add to chat
    try {
      if (typeof window.addMessage === 'function') { // Check if global addMessage exists
        window.addMessage('assistant', 'System', summaryHTML); // Use window.addMessage
        console.log("Order summary added to chat via global addMessage");
      } else {
        const chatMessagesEl = document.getElementById('chat-messages'); // Renamed
        if (chatMessagesEl) {
          const messageDiv = document.createElement('div');
          messageDiv.className = 'message assistant'; // Assuming these classes are defined in main CSS
          
          const avatarSrc = window.avatars && window.avatars['System'] ? 
                          window.avatars['System'] : '/static/images/system-avatar.png'; // Default avatar
          
          messageDiv.innerHTML = `
            <div class="agent-avatar" style="background-image: url('${avatarSrc}')"></div>
            <div class="bubble">
              <div class="name">System</div>
              ${summaryHTML}
            </div>
          `;
          
          chatMessagesEl.appendChild(messageDiv);
          chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
          console.log("Order summary directly added to chat area");
        } else {
          console.error("Chat messages area not found. Displaying as notification.");
          showNotification(`Order placed! ID: ${orderId}. Total: ¥${typeof totalPrice === 'number' ? totalPrice.toFixed(2) : totalPrice}`, 'success');
        }
      }
    } catch (e) {
      console.error("Error adding order summary to chat:", e);
      showNotification(`Order placed! ID: ${orderId}. Total: ¥${typeof totalPrice === 'number' ? totalPrice.toFixed(2) : totalPrice}`, 'success');
    }
}
  
  // Format chemical display (not directly used in summary but kept for utility)
  function formatChemicalDisplay(item) {
    if (!item || !item.text) return 'Invalid item';
    if (!item.formula) return item.text;
    
    let displayText = '';
    if (item.quantity) {
      displayText += `${item.quantity} `;
    }
    displayText += `${item.name || item.text} `; // Fallback to item.text if name is missing
    
    const formattedFormula = item.formula.replace(/(\d+)/g, (match) => {
      return Array.from(match).map(digit => {
        const subscripts = ['₀', '₁', '₂', '₃', '₄', '₅', '₆', '₇', '₈', '₉'];
        return subscripts[parseInt(digit)];
      }).join('');
    });
    displayText += `(${formattedFormula})`;
    return displayText;
  }
  
  // Generate Order ID (fallback)
  function generateOrderId(supplierCode) {
    const prefixes = {
      'sigma': 'SIG', 'fisher': 'FSH', 'vwr': 'VWR', 'alfa': 'ALF',
      'acros': 'ACR', 'tci': 'TCI', 'jt': 'JTB', 'aladdin': 'ALD',
      'macklin': 'MCK', 'bideph': 'BDP'
    };
    const prefix = prefixes[supplierCode] || 'ORD';
    const randomNum = Math.floor(10000 + Math.random() * 90000);
    const datePart = new Date().toISOString().slice(2, 10).replace(/-/g, '');
    return `${prefix}-${datePart}-${randomNum}`;
  }
  
  // Get Estimated Delivery Days (fallback)
  function getEstimatedDeliveryDays(supplierCode) {
    const deliveryTimes = {
      'sigma': [3, 5], 'fisher': [2, 4], 'vwr': [2, 5], 'alfa': [3, 6],
      'acros': [4, 7], 'tci': [5, 10], 'jt': [3, 5], 'aladdin': [1, 3],
      'macklin': [1, 3], 'bideph': [2, 4]
    };
    const [min, max] = deliveryTimes[supplierCode] || [3, 7];
    return Math.floor(min + Math.random() * (max - min + 1));
  }
  
  // Format Date
  function formatDate(date) {
    const year = date.getFullYear();
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const day = date.getDate().toString().padStart(2, '0');
    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']; // English
    const weekday = weekdays[date.getDay()];
    return `${year}-${month}-${day} (${weekday})`;
  }
  
  // Show notification message
  function showNotification(message, type = 'info') {
    const existingNotification = document.querySelector('.chem-notification');
    if (existingNotification) {
      existingNotification.remove(); // Remove previous notification first
    }
    
    const notification = document.createElement('div');
    notification.className = `chem-notification ${type}`; // Class for potential global styling
    notification.innerHTML = `
      <div class="notification-icon" style="font-size: 1.2rem; margin-right: 8px;">
        ${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}
      </div>
      <div class="notification-message">${message}</div>
    `;
    
    Object.assign(notification.style, {
      position: 'fixed',
      top: '20px',
      right: '20px',
      backgroundColor: type === 'success' ? '#ecfdf5' : type === 'error' ? '#fef2f2' : '#eff6ff', // Tailwind-like colors
      borderLeft: `4px solid ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'}`,
      padding: '12px 16px',
      borderRadius: '6px',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
      display: 'flex',
      alignItems: 'center',
      zIndex: 10000, // Ensure it's on top
      transition: 'opacity 0.3s ease, transform 0.3s ease',
      opacity: '0',
      transform: 'translateX(100%)' // Start off-screen
    });
    
    Object.assign(notification.querySelector('.notification-message').style, {
      fontFamily: "'Roboto', sans-serif", // Consistent font
      fontSize: '0.9rem',
      color: type === 'success' ? '#065f46' : type === 'error' ? '#991b1b' : '#1e40af' // Darker text for readability
    });
    
    document.body.appendChild(notification);
    
    setTimeout(() => { // Animate in
      notification.style.opacity = '1';
      notification.style.transform = 'translateX(0)';
    }, 10);
    
    setTimeout(() => { // Animate out
      notification.style.opacity = '0';
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (notification.parentNode) {
          notification.remove();
        }
      }, 300); // Remove from DOM after animation
    }, 5000); // Auto-close after 5 seconds
  }
  
  console.log("Optimized Chemical Purchasing Widget initialized successfully.");
}

// Debug function (can be removed in production)
function makeWidgetTriggerVisible() {
  setTimeout(() => {
    const triggerArea = document.querySelector('.widget-trigger-area');
    if (triggerArea) {
      // Temporarily make trigger area visible for debugging
      // triggerArea.style.backgroundColor = 'rgba(255, 0, 0, 0.1)'; // Uncomment for visual debugging
      console.log("Trigger area position (for debugging):", triggerArea.getBoundingClientRect());
    }
  }, 1000);
}

// Call after DOM is loaded (can be removed in production)
document.addEventListener('DOMContentLoaded', function() {
  // setTimeout(makeWidgetTriggerVisible, 1000); // Uncomment for visual debugging of trigger area
});
