import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
import threading

# Bot Configuration
BOT_TOKEN = "8451064449:AAEPx61lC2inHPtHaf3XVoMcSdmopJqJSpg"  # Replace with your actual bot token
ADMIN_ID = 6577308099

# Website URLs
LOGIN_URL = "https://www.abcproxy.com/login.html"
BASE_URL = "https://www.abcproxy.com"
MONITOR_URL = "https://www.abcproxy.com/center/getproxy.html?tab=account"

# Global session management
last_refresh_time = None
session_lock = threading.Lock()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_activity.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ABCProxyMonitorBot:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.application = None
        
    def initialize_driver(self):
        """Initialize the WebDriver with proper Chrome options"""
        try:
            chrome_options = Options()
            
            # Remove headless mode to see browser
            # chrome_options.add_argument("--headless")  # Comment this line to see browser
            
            # Additional options for better compatibility
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # Initialize driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            self.wait = WebDriverWait(self.driver, 20)
            logger.info("✅ Driver initialized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize driver: {e}")
            return False

    def open_login_url(self):
        """Open the login URL"""
        try:
            logger.info("🌐 Opening login URL...")
            self.driver.get(LOGIN_URL)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            logger.info("✅ Login page loaded successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to open login URL: {e}")
            return False

    def wait_for_manual_login(self):
        """Wait for manual login by user"""
        try:
            logger.info("🔐 Please login manually in the browser window...")
            logger.info("⌛ Waiting for login completion...")
            
            # Store the original URL
            original_url = self.driver.current_url
            logger.info(f"🔗 Current URL: {original_url}")
            
            # Wait for URL to change (indicating successful login)
            login_success = False
            for i in range(300):  # Wait up to 5 minutes
                current_url = self.driver.current_url
                if current_url != original_url and "login" not in current_url.lower():
                    login_success = True
                    break
                time.sleep(1)
                if i % 30 == 0:  # Log every 30 seconds
                    logger.info(f"⏳ Still waiting for login... ({i+1}/300 seconds)")
            
            if login_success:
                logger.info(f"✅ Login successful! Current URL: {self.driver.current_url}")
                return True
            else:
                logger.warning("⚠️ Login timeout reached")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error during login wait: {e}")
            return False

    def navigate_to_monitor_page(self):
        """Navigate to the account monitor page"""
        try:
            logger.info("🔄 Navigating to monitor page...")
            self.driver.get(MONITOR_URL)
            
            # Wait for account table to load with multiple possible selectors
            selectors = [
                (By.CLASS_NAME, "all_acu_box"),
                (By.CLASS_NAME, "all_acu"),
                (By.TAG_NAME, "table"),
                (By.CSS_SELECTOR, "div[class*='acu']")
            ]
            
            for by, selector in selectors:
                try:
                    self.wait.until(EC.presence_of_element_located((by, selector)))
                    logger.info(f"✅ Monitor page loaded successfully (found: {selector})")
                    return True
                except:
                    continue
            
            logger.error("❌ Could not find account table on monitor page")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to navigate to monitor page: {e}")
            return False

    def refresh_session_if_needed(self):
        """Refresh browser session every 30 minutes"""
        global last_refresh_time
        
        with session_lock:
            current_time = datetime.now()
            if (last_refresh_time is None or 
                (current_time - last_refresh_time) > timedelta(minutes=30)):
                
                logger.info("🔄 Refreshing browser session (30 minutes interval)")
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                
                # Reinitialize everything
                if not self.initialize_driver():
                    return False
                if not self.open_login_url():
                    return False
                if not self.wait_for_manual_login():
                    return False
                if not self.navigate_to_monitor_page():
                    return False
                
                last_refresh_time = current_time
                logger.info("✅ Browser session refreshed successfully")
            else:
                logger.info("✅ Using existing browser session")
            
            return True

    def extract_account_name(self, user_input):
        """Extract account name from various input formats"""
        try:
            cleaned_input = user_input.strip()
            
            # Pattern 1: Full proxy string with colons
            if ":" in cleaned_input:
                parts = cleaned_input.split(":")
                if len(parts) >= 3:
                    account_part = parts[2]
                    if "-zone-" in account_part:
                        account_name = account_part.split("-zone-")[0]
                    else:
                        account_name = account_part
                    logger.info(f"✅ Extracted account name: {account_name}")
                    return account_name
            
            # Pattern 2: Direct account name
            logger.info(f"✅ Using direct account name: {cleaned_input}")
            return cleaned_input
            
        except Exception as e:
            logger.error(f"❌ Error extracting account name: {e}")
            return user_input.strip()

    def search_account_in_table(self, account_name):
        """Search for account in the account table"""
        try:
            logger.info(f"🔍 Searching for account: {account_name}")
            
            # Wait for table to load completely
            time.sleep(3)
            
            # Try different selectors for account rows
            selectors = [
                ".all_acu_box > div",
                ".all_acu div",
                "table tr",
                "[class*='acu'] div"
            ]
            
            account_rows = []
            for selector in selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if rows:
                        account_rows = rows
                        logger.info(f"✅ Found {len(account_rows)} rows using selector: {selector}")
                        break
                except:
                    continue
            
            if not account_rows:
                logger.warning("❌ No account rows found in table")
                return None
            
            for row in account_rows:
                try:
                    # Look for account name in the row text
                    row_text = row.text
                    if account_name in row_text:
                        logger.info(f"✅ Account found: {account_name}")
                        return self.extract_account_data(row, account_name)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error checking row: {e}")
                    continue
            
            logger.warning(f"⚠️ Account not found: {account_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error searching account table: {e}")
            return None

    def extract_account_data(self, row, account_name):
        """Extract account data from table row"""
        try:
            row_text = row.text
            logger.info(f"📄 Row text: {row_text}")
            
            # Extract data using regex patterns
            traffic_limit_match = re.search(r'Traffic usage limit[\s\S]*?(\d+\.?\d*)', row_text)
            traffic_usage_match = re.search(r'Traffic consumption[\s\S]*?(\d+\.?\d*)', row_text)
            add_time_match = re.search(r'Add time[\s\S]*?(\d{4}-\d{2}-\d{2})', row_text)
            status_match = re.search(r'Status[\s\S]*?(Enable|Disable|Active|Inactive)', row_text, re.IGNORECASE)
            
            account_data = {
                'account_name': account_name,
                'traffic_limit_gb': traffic_limit_match.group(1) if traffic_limit_match else "0",
                'traffic_usage_mb': traffic_usage_match.group(1) if traffic_usage_match else "0",
                'add_time': add_time_match.group(1) if add_time_match else "N/A",
                'status': status_match.group(1) if status_match else "Unknown"
            }
            
            logger.info(f"📊 Account data extracted: {account_data}")
            return account_data
            
        except Exception as e:
            logger.error(f"❌ Error extracting account data: {e}")
            return None

    def calculate_traffic_left(self, limit_gb, usage_mb):
        """Calculate remaining traffic in MB"""
        try:
            limit_gb_float = float(limit_gb)
            usage_mb_float = float(usage_mb)
            
            # Convert GB to MB (1 GB = 1024 MB)
            limit_mb = limit_gb_float * 1024
            left_mb = limit_mb - usage_mb_float
            
            return left_mb
        except:
            return 0.00

    def calculate_usage_percentage(self, limit_gb, usage_mb):
        """Calculate usage percentage"""
        try:
            limit_gb_float = float(limit_gb)
            usage_mb_float = float(usage_mb)
            
            if limit_gb_float == 0:
                return 0
                
            limit_mb = limit_gb_float * 1024
            
            if limit_mb == 0:
                return 0
                
            percentage = (usage_mb_float / limit_mb) * 100
            return min(percentage, 100)
        except:
            return 0

    def format_traffic_limit(self, limit_gb):
        """Format traffic limit with GB unit"""
        try:
            return f"{float(limit_gb):.0f} GB" if float(limit_gb).is_integer() else f"{limit_gb} GB"
        except:
            return "0 GB"

    def format_traffic_usage(self, usage_mb):
        """Format traffic usage with MB unit"""
        try:
            return f"{float(usage_mb):.2f} MB"
        except:
            return "0.00 MB"

    def format_traffic_left(self, left_mb):
        """Format remaining traffic"""
        try:
            return f"{left_mb:.2f} MB"
        except:
            return "0.00 MB"

    def get_usage_emoji(self, percentage):
        """Get emoji based on usage percentage"""
        if percentage < 50:
            return "🟢"
        elif percentage < 80:
            return "🟡"
        else:
            return "🔴"

    def format_account_message(self, account_data):
        """Format account overview message"""
        try:
            left_mb = self.calculate_traffic_left(
                account_data['traffic_limit_gb'], 
                account_data['traffic_usage_mb']
            )
            
            usage_percentage = self.calculate_usage_percentage(
                account_data['traffic_limit_gb'], 
                account_data['traffic_usage_mb']
            )
            
            formatted_limit = self.format_traffic_limit(account_data['traffic_limit_gb'])
            formatted_usage = self.format_traffic_usage(account_data['traffic_usage_mb'])
            formatted_left = self.format_traffic_left(left_mb)
            
            status_icon = "🟢" if "enable" in account_data['status'].lower() else "🔴"
            usage_emoji = self.get_usage_emoji(usage_percentage)
            
            message = f"""
╔═━Account Overview━═╗
┣🌐 Username ➜ {account_data['account_name']}
┣🔐 Reg. Date ➜ {account_data['add_time']}
┣🪝Limit ➜ {formatted_limit}
┣🟥 Usage ➜ {formatted_usage}
┣🟩 Left ➜ {formatted_left}
╚═━━ ◢◤ ABC ◥◣ ━━━═╝
            """.strip()
            
            # Create inline keyboard with percentage
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{usage_emoji} {usage_percentage:.1f}% Used | {status_icon} Active", 
                    callback_data="do_nothing"
                )
            ]])
            
            return message, keyboard
            
        except Exception as e:
            logger.error(f"❌ Error formatting message: {e}")
            return "❌ Error formatting account information", None

    def process_multiple_accounts(self, account_names):
        """Process multiple accounts in one session"""
        results = {}
        
        try:
            # Refresh session if needed
            if not self.refresh_session_if_needed():
                return {name: (None, "❌ Session refresh failed") for name in account_names}
            
            for account_name in account_names:
                logger.info(f"🔍 Processing account: {account_name}")
                
                account_data = self.search_account_in_table(account_name)
                
                if account_data:
                    message, keyboard = self.format_account_message(account_data)
                    results[account_name] = (message, keyboard)
                    logger.info(f"✅ Account processed: {account_name}")
                else:
                    results[account_name] = (None, "🚫 Your input is invalid or not registered in our system records.")
                    logger.warning(f"⚠️ Account not found: {account_name}")
                
                time.sleep(2)  # Increased delay for stability
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error processing multiple accounts: {e}")
            return {name: (None, f"❌ System error: {str(e)}") for name in account_names}

    def run_account_check(self, account_names):
        """Main method to run account check for multiple accounts"""
        try:
            if not self.driver:
                logger.info("🔄 Initializing new browser session...")
                if not self.initialize_driver():
                    return {name: (None, "❌ Failed to initialize browser") for name in account_names}
                
                if not self.open_login_url():
                    return {name: (None, "❌ Failed to open login page") for name in account_names}
                
                if not self.wait_for_manual_login():
                    return {name: (None, "❌ Login failed or timeout") for name in account_names}
                
                if not self.navigate_to_monitor_page():
                    return {name: (None, "❌ Failed to navigate to monitor page") for name in account_names}
            
            results = self.process_multiple_accounts(account_names)
            return results
            
        except Exception as e:
            logger.error(f"❌ Error in account check: {e}")
            return {name: (None, f"❌ System error: {str(e)}") for name in account_names}

    # Telegram Bot Methods
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message when the command /start is issued."""
        welcome_message = """
🤖 *Welcome to ABC Proxy Account Monitor Bot!*

*How to use this bot:*
1. Send your account name or proxy string
2. Send multiple accounts (one per line) for batch checking
3. The bot will sync with ABC Cloud System
4. Get your account overview instantly

*Supported input formats:*
- `anam1gbPL2510` (direct account name)
- `as.domain.com:4950:anam1gbPL2510-zone-region:password` (full proxy string)

*Multiple accounts example:*
•anam1gbPL2510
•testuser123
•as.domain.com:4950:user456-zone-region:pass

*Features:*
• Account traffic usage with percentage
• Registration date
• Status monitoring
• Real-time updates
• Multi-account support

*Start by sending your account name or proxy string!*
        """
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_account_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle account query messages"""
        user_input = update.message.text.strip()
        chat_id = update.message.chat_id
        
        if not user_input:
            await update.message.reply_text("❌ Please provide an account name or proxy string.")
            return
        
        # Extract account names (support multiple lines)
        input_lines = user_input.split('\n')
        account_names = []
        
        for line in input_lines:
            line = line.strip()
            if line:
                account_name = self.extract_account_name(line)
                if account_name:
                    account_names.append(account_name)
        
        if not account_names:
            await update.message.reply_text("❌ No valid account names found in your input.")
            return
        
        # Send loading message with countdown
        loading_text = f"🤖 Syncing with ABC Cloud System...\n📊 Checking {len(account_names)} account(s)...(10s)"
        loading_message = await update.message.reply_text(loading_text)
        
        # Countdown animation
        for i in range(9, 0, -1):
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=loading_message.message_id,
                    text=f"🤖 Syncing with ABC Cloud System...\n📊 Checking {len(account_names)} account(s)...({i}s)"
                )
                await asyncio.sleep(1)
            except:
                pass
        
        # Process all accounts
        results = self.run_account_check(account_names)
        
        # Send results
        success_count = 0
        for account_name, (message, keyboard) in results.items():
            if message and keyboard:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                success_count += 1
            else:
                error_msg = keyboard if keyboard else "❌ Unknown error"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 Account: {account_name}\n{error_msg}"
                )
        
        # Delete loading message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
        except:
            pass
        
        # Send summary
        if success_count > 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Successfully processed {success_count} out of {len(account_names)} account(s)"
            )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle broadcast messages from admin"""
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Unauthorized access.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Usage: /broadcast <message>")
            return
        
        broadcast_text = " ".join(context.args)
        
        await update.message.reply_text(
            f"📢 Broadcast message prepared:\n\n{broadcast_text}\n\n"
            f"*This would be sent to all users.*",
            parse_mode=ParseMode.MARKDOWN
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot status and session info"""
        global last_refresh_time
        
        status_message = f"""
🤖 *Bot Status Overview*

*Session Information:*
• Last Refresh: {last_refresh_time.strftime('%Y-%m-%d %H:%M:%S') if last_refresh_time else 'Never'}
• Next Refresh: {(last_refresh_time + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S') if last_refresh_time else 'N/A'}
• Browser Active: {'✅ Yes' if self.driver else '❌ No'}

*Features:*
• Multi-account support ✅
• Auto-refresh every 30 minutes ✅
• Percentage-based usage display ✅
• Error handling and recovery ✅

*Usage:*
Send account names (one per line) for batch checking!
        """
        
        await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)

    def setup_handlers(self):
        """Setup Telegram bot handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("broadcast", self.broadcast_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Message handlers
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_account_query
        ))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    def run_bot(self):
        """Run the Telegram bot"""
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        
        logger.info("🤖 Bot is running...")
        self.application.run_polling()

def main():
    """Main function"""
    print("🚀 Starting ABC Proxy Account Monitor Bot...")
    print("📝 Make sure to replace 'YOUR_BOT_TOKEN_HERE' with your actual bot token")
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your bot token in the BOT_TOKEN variable")
        return
    
    # Create and run the bot
    bot = ABCProxyMonitorBot()
    bot.run_bot()

if __name__ == "__main__":
    main()
