import asyncio
import logging
import re
import time
from datetime import datetime, timedelta
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
import threading
import json

# Bot Configuration
BOT_TOKEN = "8451064449:AAEPx61lC2inHPtHaf3XVoMcSdmopJqJSpg"
ADMIN_ID = 6577308099

# Website URLs
LOGIN_URL = "https://www.abcproxy.com/login.html"
BASE_URL = "https://www.abcproxy.com"
MONITOR_URL = "https://www.abcproxy.com/center/getproxy.html?tab=account"

# Global session management
last_refresh_time = None
session_lock = threading.Lock()
is_logged_in = False
login_event = threading.Event()

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
        self.is_initialized = False
        self.session_start_time = None
        
    def initialize_driver(self):
        """Initialize the WebDriver"""
        try:
            self.driver = Driver(uc=True, headless=False)
            self.wait = WebDriverWait(self.driver, 30)
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
        global is_logged_in
        
        try:
            logger.info("🔐 PLEASE LOGIN MANUALLY IN THE BROWSER WINDOW!")
            logger.info("⏳ Waiting for you to complete login...")
            logger.info("✅ Bot will start automatically after successful login")
            
            original_url = self.driver.current_url
            
            # Wait for URL change indicating successful login
            WebDriverWait(self.driver, 300).until(
                lambda driver: driver.current_url != original_url and 
                              "login" not in driver.current_url.lower() and
                              "center" in driver.current_url.lower()
            )
            
            is_logged_in = True
            login_event.set()
            logger.info(f"✅ Login successful! Current URL: {self.driver.current_url}")
            return True
            
        except TimeoutException:
            logger.error("❌ Login timeout reached. Please restart the script and login within 5 minutes.")
            return False
        except Exception as e:
            logger.error(f"❌ Error during login wait: {e}")
            return False

    def navigate_to_monitor_page(self):
        """Navigate to the account monitor page"""
        try:
            logger.info("🔄 Navigating to monitor page...")
            
            # Check if we're already on monitor page
            if MONITOR_URL in self.driver.current_url:
                logger.info("✅ Already on monitor page")
                return True
                
            self.driver.get(MONITOR_URL)
            
            # Wait for the page to load completely
            time.sleep(5)
            
            # Wait for the main container to load
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "acu_admin")))
            
            logger.info("✅ Monitor page loaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to navigate to monitor page: {e}")
            return False

    def wait_for_account_data(self):
        """Wait for account data to load dynamically"""
        try:
            logger.info("⏳ Waiting for account data to load...")
            
            # Wait for account rows to be populated
            max_attempts = 10
            for attempt in range(max_attempts):
                # Try to find account rows using multiple selectors
                account_rows = self.driver.find_elements(By.CSS_SELECTOR, ".all_acu_box > div")
                
                if len(account_rows) > 0:
                    logger.info(f"✅ Found {len(account_rows)} account rows")
                    return True
                
                # Also check if there's a "no data" message
                no_data_elements = self.driver.find_elements(By.CLASS_NAME, "not_Data_Center_Box")
                if no_data_elements:
                    logger.info("ℹ️ No accounts found (empty account list)")
                    return True
                
                logger.info(f"🔄 Attempt {attempt + 1}/{max_attempts}: No account data found, waiting...")
                time.sleep(3)
                
                # Try to trigger data load by clicking or scrolling if needed
                if attempt == 3:
                    logger.info("🔄 Trying to trigger data load...")
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    self.driver.execute_script("window.scrollTo(0, 0);")
            
            logger.error("❌ No account data loaded after multiple attempts")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error waiting for account data: {e}")
            return False

    def get_account_data_via_javascript(self):
        """Extract account data using JavaScript execution"""
        try:
            logger.info("🔍 Extracting account data via JavaScript...")
            
            # Execute JavaScript to get all account rows and their content
            script = """
            var accounts = [];
            var rows = document.querySelectorAll('.all_acu_box > div');
            
            rows.forEach(function(row, index) {
                var spans = row.querySelectorAll('span');
                var accountData = {
                    index: index,
                    account_name: spans[0] ? spans[0].textContent.trim() : '',
                    password: spans[1] ? spans[1].textContent.trim() : '',
                    traffic_limit: spans[2] ? spans[2].textContent.trim() : '',
                    traffic_usage: spans[3] ? spans[3].textContent.trim() : '',
                    add_time: spans[4] ? spans[4].textContent.trim() : '',
                    status: spans[5] ? spans[5].textContent.trim() : '',
                    remark: spans[6] ? spans[6].textContent.trim() : ''
                };
                accounts.push(accountData);
            });
            
            return accounts;
            """
            
            accounts_data = self.driver.execute_script(script)
            logger.info(f"📊 Extracted {len(accounts_data)} accounts via JavaScript")
            
            return accounts_data
            
        except Exception as e:
            logger.error(f"❌ Error extracting data via JavaScript: {e}")
            return []

    def search_account_by_name(self, account_name, accounts_data):
        """Search for account in the extracted data"""
        try:
            logger.info(f"🔍 Searching for account: {account_name}")
            
            for account in accounts_data:
                if account_name.lower() in account['account_name'].lower():
                    logger.info(f"✅ Account found: {account['account_name']}")
                    return account
            
            logger.warning(f"⚠️ Account not found: {account_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error searching account: {e}")
            return None

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

    def setup_browser_session(self):
        """Setup browser session with login"""
        global is_logged_in
        
        try:
            logger.info("🚀 Setting up browser session...")
            
            if not self.initialize_driver():
                return False
                
            if not self.open_login_url():
                return False
                
            if not self.wait_for_manual_login():
                return False
                
            if not self.navigate_to_monitor_page():
                return False
                
            self.is_initialized = True
            self.session_start_time = datetime.now()
            logger.info("✅ Browser session setup completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Browser session setup failed: {e}")
            return False

    def check_session_validity(self):
        """Check if session is still valid"""
        try:
            self.driver.get(MONITOR_URL)
            time.sleep(2)
            
            if "login" in self.driver.current_url.lower():
                logger.warning("⚠️ Session expired")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking session validity: {e}")
            return False

    def refresh_session_if_needed(self):
        """Refresh browser session only when needed"""
        global last_refresh_time
        
        with session_lock:
            current_time = datetime.now()
            
            if not self.check_session_validity():
                logger.info("🔄 Session invalid, refreshing...")
                if self.driver:
                    self.driver.quit()
                
                if not self.setup_browser_session():
                    return False
                
                last_refresh_time = current_time
                return True
            
            if (last_refresh_time is None or 
                (current_time - last_refresh_time) > timedelta(minutes=60)):
                
                logger.info("🔄 Periodic refresh (60 minutes interval)")
                self.driver.refresh()
                time.sleep(3)
                last_refresh_time = current_time
            
            return True

    def clean_traffic_value(self, value):
        """Clean traffic values"""
        try:
            if not value or value == "N/A":
                return "0"
            
            cleaned = re.sub(r'[^\d.]', '', value)
            return cleaned if cleaned else "0"
        except:
            return "0"

    def calculate_traffic_left(self, limit_gb, usage_mb):
        """Calculate remaining traffic in MB"""
        try:
            limit_gb_float = float(limit_gb)
            usage_mb_float = float(usage_mb)
            
            limit_mb = limit_gb_float * 1024
            left_mb = limit_mb - usage_mb_float
            
            return max(left_mb, 0)
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
        """Format traffic limit"""
        try:
            limit_float = float(limit_gb)
            if limit_float == 0:
                return "Unlimited"
            return f"{limit_float:.0f} GB" if limit_float.is_integer() else f"{limit_float} GB"
        except:
            return "0 GB"

    def format_traffic_usage(self, usage_mb):
        """Format traffic usage"""
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
                account_data['traffic_limit'], 
                account_data['traffic_usage']
            )
            
            usage_percentage = self.calculate_usage_percentage(
                account_data['traffic_limit'], 
                account_data['traffic_usage']
            )
            
            formatted_limit = self.format_traffic_limit(account_data['traffic_limit'])
            formatted_usage = self.format_traffic_usage(account_data['traffic_usage'])
            formatted_left = self.format_traffic_left(left_mb)
            
            status_icon = "🟢" if "enable" in account_data['status'].lower() else "🔴"
            usage_emoji = self.get_usage_emoji(usage_percentage)
            
            message = f"""
╔══━━ Account Overview ━━══╗
┃
┣🌐 Username ➜ {account_data['account_name']}
┣📅 Reg. Date ➜ {account_data['add_time']}
┣📊 Limit ➜ {formatted_limit}
┣🔴 Usage ➜ {formatted_usage}
┣🟢 Left ➜ {formatted_left}
┃
╚══━━ ◢◤ ABC ◥◣ ━━══╝
            """.strip()
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    f"{usage_emoji} {usage_percentage:.1f}% Used | {status_icon} {account_data['status']}", 
                    callback_data="do_nothing"
                )
            ]])
            
            return message, keyboard
            
        except Exception as e:
            logger.error(f"❌ Error formatting message: {e}")
            return "❌ Error formatting account information", None

    def debug_page_content(self):
        """Debug method to see page content"""
        try:
            logger.info("🔍 Debugging page content...")
            
            # Get page HTML
            page_html = self.driver.page_source
            
            # Check for specific elements
            elements_to_check = [
                ".all_acu_box",
                ".all_acu_box > div",
                ".not_Data_Center_Box",
                ".acu_admin"
            ]
            
            for selector in elements_to_check:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                logger.info(f"🔍 Selector '{selector}': found {len(elements)} elements")
                
                for i, element in enumerate(elements):
                    logger.info(f"  Element {i}: {element.text[:100]}...")
            
            # Check if there's any JavaScript error
            console_logs = self.driver.get_log('browser')
            if console_logs:
                logger.info("🔍 Browser console logs:")
                for log in console_logs:
                    logger.info(f"  {log}")
                    
        except Exception as e:
            logger.error(f"❌ Debug error: {e}")

    def process_multiple_accounts(self, account_names):
        """Process multiple accounts in one session"""
        results = {}
        
        try:
            if not self.refresh_session_if_needed():
                return {name: (None, "❌ Session refresh failed") for name in account_names}
            
            # Wait for account data to load
            if not self.wait_for_account_data():
                logger.error("❌ Failed to load account data")
                return {name: (None, "❌ Failed to load account data") for name in account_names}
            
            # Debug page content
            self.debug_page_content()
            
            # Extract account data via JavaScript
            accounts_data = self.get_account_data_via_javascript()
            
            if not accounts_data:
                logger.error("❌ No account data extracted")
                return {name: (None, "❌ No accounts found in system") for name in account_names}
            
            for account_name in account_names:
                logger.info(f"🔍 Processing account: {account_name}")
                
                account_data = self.search_account_by_name(account_name, accounts_data)
                
                if account_data:
                    # Clean the data
                    account_data['traffic_limit'] = self.clean_traffic_value(account_data['traffic_limit'])
                    account_data['traffic_usage'] = self.clean_traffic_value(account_data['traffic_usage'])
                    
                    message, keyboard = self.format_account_message(account_data)
                    results[account_name] = (message, keyboard)
                    logger.info(f"✅ Account processed: {account_name}")
                else:
                    results[account_name] = (None, "🚫 Account not found in system")
                    logger.warning(f"⚠️ Account not found: {account_name}")
                
                time.sleep(1)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error processing multiple accounts: {e}")
            return {name: (None, f"❌ System error: {str(e)}") for name in account_names}

    def run_account_check(self, account_names):
        """Main method to run account check"""
        try:
            if not self.is_initialized:
                return {name: (None, "❌ Bot is not ready. Please wait for login completion.") for name in account_names}
            
            results = self.process_multiple_accounts(account_names)
            return results
            
        except Exception as e:
            logger.error(f"❌ Error in account check: {e}")
            return {name: (None, f"❌ System error: {str(e)}") for name in account_names}

    # Telegram Bot Methods
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message"""
        global is_logged_in
        
        if not is_logged_in:
            await update.message.reply_text("⏳ Bot is initializing... Please wait for login completion.")
            return
        
        welcome_message = """
🤖 Welcome to ABC Proxy Account Monitor Bot!

How to use:
1. Send account name or proxy string
2. Send multiple accounts (one per line)
3. Get instant account overview

Supported formats:
- accountname (direct)
- proxy.com:port:accountname-zone:password (full)

Start by sending your account name!
        """
        
        await update.message.reply_text(welcome_message)

    async def handle_account_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle account query messages"""
        global is_logged_in
        
        if not is_logged_in:
            await update.message.reply_text("❌ Bot is not ready yet. Please wait for login completion.")
            return
            
        user_input = update.message.text.strip()
        chat_id = update.message.chat_id
        
        if not user_input:
            await update.message.reply_text("❌ Please provide an account name.")
            return
        
        input_lines = user_input.split('\n')
        account_names = []
        
        for line in input_lines:
            line = line.strip()
            if line:
                account_name = self.extract_account_name(line)
                if account_name:
                    account_names.append(account_name)
        
        if not account_names:
            await update.message.reply_text("❌ No valid account names found.")
            return
        
        loading_text = f"🤖 Checking {len(account_names)} account(s)...(10s)"
        loading_message = await update.message.reply_text(loading_text)
        
        for i in range(9, 0, -1):
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=loading_message.message_id,
                    text=f"🤖 Checking {len(account_names)} account(s)...({i}s)"
                )
                await asyncio.sleep(1)
            except:
                pass
        
        results = self.run_account_check(account_names)
        
        success_count = 0
        for account_name, (message, keyboard) in results.items():
            if message and keyboard:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=keyboard
                )
                success_count += 1
            else:
                error_msg = keyboard if keyboard else "❌ Unknown error"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 {account_name}\n{error_msg}"
                )
        
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=loading_message.message_id)
        except:
            pass
        
        if success_count > 0:
            summary_msg = f"✅ Processed {success_count}/{len(account_names)} accounts"
            if success_count < len(account_names):
                summary_msg += f"\n❌ {len(account_names) - success_count} not found"
            await context.bot.send_message(chat_id=chat_id, text=summary_msg)

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot status"""
        global last_refresh_time, is_logged_in
        
        status_message = f"""
🤖 Bot Status

• Login: {'✅' if is_logged_in else '❌'}
• Session: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S') if self.session_start_time else 'N/A'}
• Browser: {'✅' if self.driver else '❌'}

Send account names to check!
        """
        
        await update.message.reply_text(status_message)

    def setup_handlers(self):
        """Setup Telegram bot handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_account_query))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

    def run_bot(self):
        """Run the Telegram bot"""
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
        logger.info("🤖 Bot is running...")
        self.application.run_polling()

def setup_browser_in_thread(bot):
    """Setup browser session in a separate thread"""
    def browser_setup():
        success = bot.setup_browser_session()
        if success:
            logger.info("✅ Browser setup completed. Bot is now ready!")
            print("\n" + "="*50)
            print("✅ BOT IS READY TO USE!")
            print("📱 Now you can send account names to the Telegram bot")
            print("="*50)
        else:
            logger.error("❌ Browser setup failed. Please restart.")
            print("\n❌ Browser setup failed. Please restart.")
    
    browser_thread = threading.Thread(target=browser_setup, daemon=True)
    browser_thread.start()
    return browser_thread

def main():
    """Main function"""
    print("🚀 Starting ABC Proxy Account Monitor Bot...")
    print("=" * 60)
    print("📋 IMPORTANT:")
    print("1. Browser will open - LOGIN MANUALLY")
    print("2. Wait for 'Login successful' message")
    print("3. Then use Telegram bot")
    print("=" * 60)
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Please set your bot token")
        return
    
    bot = ABCProxyMonitorBot()
    
    print("🔄 Starting browser session...")
    browser_thread = setup_browser_in_thread(bot)
    
    time.sleep(3)
    
    print("🤖 Starting Telegram bot...")
    try:
        bot.run_bot()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
    finally:
        if bot.driver:
            bot.driver.quit()

if __name__ == "__main__":
    main()