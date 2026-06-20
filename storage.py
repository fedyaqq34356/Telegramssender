import json
from pathlib import Path
from logger import logger


class Storage:
    def __init__(self, filepath="data.json"):
        self.filepath = Path(filepath)
        self.accounts = {}
        self.source_groups = []
        self.target_groups = []
        self.parsed_users = []
        self.admin_users = []
        self.bot_users = []
        self.invite_stats = {}
        self.broadcast_stats = {}
        self.parse_progress = {}
        self.publics = []
        self._load()

    def _load(self):
        if not self.filepath.exists():
            return
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.accounts = data.get("accounts", {})
                self.source_groups = data.get("source_groups", [])
                self.target_groups = data.get("target_groups", [])
                self.parsed_users = data.get("parsed_users", [])
                self.admin_users = data.get("admin_users", [])
                self.bot_users = data.get("bot_users", [])
                self.invite_stats = data.get("invite_stats", {})
                self.broadcast_stats = data.get("broadcast_stats", {})
                self.parse_progress = data.get("parse_progress", {})
                self.publics = data.get("publics", [])
            logger.info("Дані завантажено")
        except Exception as e:
            logger.error(f"Помилка завантаження: {e}")

    def _save(self):
        try:
            data = {
                "accounts": {k: {
                    "api_id": v["api_id"],
                    "api_hash": v["api_hash"],
                    "phone": v["phone"]
                } for k, v in self.accounts.items()},
                "source_groups": self.source_groups,
                "target_groups": self.target_groups,
                "parsed_users": self.parsed_users,
                "admin_users": self.admin_users,
                "bot_users": self.bot_users,
                "invite_stats": self.invite_stats,
                "broadcast_stats": self.broadcast_stats,
                "parse_progress": self.parse_progress,
                "publics": self.publics
            }
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Дані збережено")
        except Exception as e:
            logger.error(f"Помилка збереження: {e}")

    def add_account(self, name, api_id, api_hash, phone):
        self.accounts[name] = {"api_id": api_id, "api_hash": api_hash, "phone": phone}
        self._save()
        logger.info(f"Додано акаунт: {name}")

    def remove_account(self, name):
        if name in self.accounts:
            del self.accounts[name]
            self._save()
            logger.info(f"Видалено акаунт: {name}")

    def add_source_group(self, group):
        if group not in self.source_groups:
            self.source_groups.append(group)
            self._save()
            logger.info(f"Додано джерело: {group}")

    def add_target_group(self, group):
        if group not in self.target_groups:
            self.target_groups.append(group)
            self._save()
            logger.info(f"Додано отримувач: {group}")

    def remove_source_group(self, group):
        if group in self.source_groups:
            self.source_groups.remove(group)
            self._save()
            logger.info(f"Видалено джерело: {group}")

    def remove_target_group(self, group):
        if group in self.target_groups:
            self.target_groups.remove(group)
            self._save()
            logger.info(f"Видалено отримувач: {group}")

    def save_parsed_users(self, users, admins=None, bots=None):
        self.parsed_users = users
        if admins is not None:
            self.admin_users = admins
        if bots is not None:
            self.bot_users = bots
        self._save()
        logger.info(f"Збережено: {len(users)} юзерів, {len(admins or [])} адмінів, {len(bots or [])} ботів")

    def clear_parsed_users(self):
        self.parsed_users = []
        self.admin_users = []
        self.bot_users = []
        self._save()

    def save_parse_progress(self, group_key, offset_id, messages_checked, found_count):
        self.parse_progress[group_key] = {
            "offset_id": offset_id,
            "messages_checked": messages_checked,
            "found_count": found_count
        }
        self._save()

    def get_parse_progress(self, group_key):
        return self.parse_progress.get(group_key)

    def clear_parse_progress(self, group_key):
        if group_key in self.parse_progress:
            del self.parse_progress[group_key]
            self._save()

    def add_public(self, link, region, description=""):
        for p in self.publics:
            if p["link"] == link:
                p["region"] = region
                p["description"] = description
                self._save()
                return
        self.publics.append({
            "link": link,
            "region": region,
            "description": description,
            "users": [],
            "admin_users": [],
            "bot_users": []
        })
        self._save()
        logger.info(f"Додано паблік: {link}")

    def update_public_users(self, link, users, admins=None, bots=None):
        for p in self.publics:
            if p["link"] == link:
                p["users"] = users
                p["admin_users"] = admins or []
                p["bot_users"] = bots or []
                self._save()
                return

    def remove_public(self, idx):
        if 0 <= idx < len(self.publics):
            link = self.publics[idx]["link"]
            self.publics.pop(idx)
            self._save()
            logger.info(f"Видалено паблік: {link}")

    def get_combined_users(self, indices):
        seen = set()
        combined = []
        for i in indices:
            if 0 <= i < len(self.publics):
                for u in self.publics[i].get("users", []):
                    if u["id"] not in seen:
                        seen.add(u["id"])
                        combined.append(u)
        return combined

    def get_today_invites(self, account_name):
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        return self.invite_stats.get(account_name, {}).get(today, 0)

    def increment_invites(self, account_name):
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if account_name not in self.invite_stats:
            self.invite_stats[account_name] = {}
        self.invite_stats[account_name][today] = self.invite_stats[account_name].get(today, 0) + 1
        self._save()

    def get_today_broadcasts(self, account_name):
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        return self.broadcast_stats.get(account_name, {}).get(today, 0)

    def increment_broadcasts(self, account_name):
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
        if account_name not in self.broadcast_stats:
            self.broadcast_stats[account_name] = {}
        self.broadcast_stats[account_name][today] = self.broadcast_stats[account_name].get(today, 0) + 1
        self._save()

    def reset_old_stats(self, days=7):
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        for account in self.invite_stats:
            self.invite_stats[account] = {
                d: c for d, c in self.invite_stats[account].items() if d >= cutoff
            }
        for account in self.broadcast_stats:
            self.broadcast_stats[account] = {
                d: c for d, c in self.broadcast_stats[account].items() if d >= cutoff
            }
        self._save()


storage = Storage()