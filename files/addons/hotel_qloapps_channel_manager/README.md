# Odoo Hotel Booking Channel Manager (**hotel_qloapps_channel_manager**)

## Overview
Odoo Hotel Booking Channel Manager acts as a bridge between Odoo and popular OTA platforms like Booking.com, Expedia, Airbnb, Agoda, Google Hotels, and more. Whenever a booking is made on a connected OTA platform, the module automatically syncs the booking details to Odoo and updates inventory on all integrated channels in real time.

**Note:** This Odoo App is an extension of the Odoo Hotel Management Solution and is fully compatible with it. The price of the Odoo Hotel Booking Channel Manager includes the base module, Odoo Hotel Management Solution.

## What is QloApps Channel Manager?
QloApps Channel Manager is an integration that connects QloApps PMS with popular OTA platforms. It enables real-time synchronization of inventory, rates, restrictions, and bookings across all connected channels, ensuring accurate updates and preventing overbookings.

## Dependencies
- **hotel_management_system** module must be installed prior to using this module.

## Features
- **API Endpoints:** Fetch hotel data, room types, bookings, and more.
- **Booking Synchronization:** Automatically syncs OTA bookings to Odoo in real time.
- **Inventory Management:** Updates room availability across connected channels.
- **Secure Access:** Uses an API key for authentication to protect data.

## Installation
Follow these standard Odoo module installation steps:
1. Copy the module into your Odoo **addons** directory.
2. Restart your Odoo server.
3. Navigate to **Apps**, search for `hotel_qloapps_channel_manager`, and install it.

## Configuration
### Generating an API Key
1. Navigate to **Hotel (Main Menu)** → **Configuration** → **Web Services**.
2. Open the form and enter a name for the API key.
3. Click the **Generate Key** button.
4. A unique API key will be generated, which is required to authenticate API requests.

## API Authentication
Every API request must include the generated API key in the request headers:
```
api_key: YOUR_GENERATED_KEY
```

## API Endpoints
Key endpoints include:
- **`/api/properties`**: Fetch hotel property details.
- **`/api/room_types`**: Retrieve room type information for a given property.
- **`/api/bookings`**: Fetch booking details.
- **`/api/booking_notification` (POST)**: Create a new booking.

## Security
- API access is restricted to authenticated users via API keys.
- The module follows Odoo’s best practices to ensure secure data handling.

### Credits
- **Author:** Webkul Software Pvt. Ltd.