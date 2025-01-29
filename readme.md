# SnapShop

---

## Preloaded Data
### Admin User
- **Username:** admin  
- **Password:** admin

### Test User
- **Username:** test  
- **Password:** FT5BAk!4SM@vMny

---

## Features
### Admin
- View, add, edit, and manage products.
- View and handle return requests with approval/rejection functionality.
- Ensure stock and wallet updates for approved returns.

### User
- View available products with prices and stock levels.
- Purchase products with wallet deductions and stock adjustments.
- Request returns for purchased products (within 3 minutes of purchase).


## How to Run the Project

### 1. Clone the Repository
```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py loaddata data.json
   python manage.py runserver
