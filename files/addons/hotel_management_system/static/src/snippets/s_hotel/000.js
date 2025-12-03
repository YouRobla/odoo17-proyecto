/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import publicWidget from "@web/legacy/js/public/public_widget";
import { loadJS } from "@web/core/assets";
import { jsonrpc } from "@web/core/network/rpc_service";
import { renderToFragment } from "@web/core/utils/render";

publicWidget.registry.rooms = publicWidget.Widget.extend({
  selector: '.roomMainSection',
  disabledInEditableMode: false,
  init() {
    this._super(...arguments);
  },
  start: function () {
    var $snippet = this.$target;
    var $dynamic = $snippet.find(".selectiveRoomforhomePage")

    // -------------------------------------------------------------------------
    // Add spinner
    // -------------------------------------------------------------------------
    $dynamic.html('<div class="d-flex justify-content-center"><div class="lds-hourglass"></div></div>')
    $.get("/get/website/room", function () { }).then(function (data) {
      setTimeout(function () {
        $dynamic.html(data)
      }, 500);
    });

  },
  destroy: function () {
    this._clearContent();
    this._super.apply(this, arguments);
  },
  _clearContent: function () {
    const $templateArea = this.$el.find('.selectiveRoomforhomePage');
    this.trigger_up('widgets_stop_request', {
      $target: $templateArea,
    });
    $templateArea.html('');
  },

  // //Empty to snippet div
  _empty_$el() {
    this.$el.empty();
  }
});

publicWidget.registry.trending_rooms = publicWidget.Widget.extend({
  selector: '.trendingRoomSection',
  disabledInEditableMode: false,
  init() {
    this._super(...arguments);
  },
  start: async function () {
    var self = this;
    await loadJS("hotel_management_system/static/src/swiper/swiper-bundle.min.js");
    var $snippet = this.$target;
    var $dynamic = $snippet.find(".trending_room_data")

    // -------------------------------------------------------------------------
    // Add spinner
    // -------------------------------------------------------------------------
    $dynamic.html('<div class="d-flex justify-content-center"><div class="lds-hourglass"></div></div>')

    $.get("/get/trending/room").then(function (data) {
      setTimeout(function () {
        // self._empty_$el();
        $dynamic.html(data)
        const swiper = new Swiper(".swiper", {
          direction: "horizontal",
          loop: true,
          speed: 1500,
          slidesPerView: 4,
          spaceBetween: 60,
          mousewheel: true,
          parallax: true,
          centeredSlides: true,
          effect: "coverflow",

          coverflowEffect: {
            rotate: 40,
            slideShadows: true
          },
          autoplay: {
            delay: 2000,
            pauseOnMouseEnter: true
          },
          scrollbar: {
            el: ".swiper-scrollbar"
          },
          breakpoints: {
            0: {
              slidesPerView: 1,
              spaceBetween: 60
            },
            600: {
              slidesPerView: 2,
              spaceBetween: 60
            },
            1000: {
              slidesPerView: 3,
              spaceBetween: 60
            },
            1400: {
              slidesPerView: 4,
              spaceBetween: 60
            },
            2300: {
              slidesPerView: 5,
              spaceBetween: 60
            },
            2900: {
              slidesPerView: 6,
              spaceBetween: 60
            }
          }
        });
      }, 500);
    });
  },

  destroy: function () {
    this._clearContent(); this._super.apply(this, arguments);
  },
  _clearContent: function () {
    const $templateArea = this.$el.find('.trending_room_data');
    this.trigger_up('widgets_stop_request', {
      $target: $templateArea,
    });
    $templateArea.html('');
  },

  //Empty to snippet div
  _empty_$el() {
    this.$el.empty();
  }
});

publicWidget.registry.multi_hotel_search_ui = publicWidget.Widget.extend({
  selector: '#homepage_booking_panel',
  disabledInEditableMode: false,
  willStart: async function () {
    try {
      this.hotels = await jsonrpc(`/wk/get_hotels`);
    } catch (error) {
      console.log('Error fetching hotels:', error);
    }
  },
  start: async function () {
    let self = this;
    self.renderHotels(self.hotels);

    const travellersInput = document.getElementById('travellers-input');
    const travellersDropdown = document.getElementById('travellers-dropdown');
    const numAdultsInput = document.getElementById('wk_adult');
    const numChildrenInput = document.getElementById('wk_child');
    const checkIn = document.getElementById('check_in');
    const checkOut = document.getElementById('check_out');

    const today = new Date();
    const tomorrow = new Date();
    tomorrow.setDate(today.getDate() + 1);
    
    const formatDate = (date) => {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        return `${month}/${day}/${year}`;
    };
    
    checkIn.value = formatDate(today);
    checkOut.value = formatDate(tomorrow);
    travellersInput.addEventListener("click", () => {
      travellersDropdown.style.display = 'flex';
    });

    const updateTotalTravellers = () => {
      const numAdults = parseInt(numAdultsInput.value, 10) || 0;
      const numChildren = parseInt(numChildrenInput.value, 10) || 0;
      const totalTravellers = numAdults + numChildren;
      travellersInput.value = `${totalTravellers} Member${totalTravellers !== 1 ? 's' : ''}`;
    };

    // Calculating total travelers after re-routing to the home page
    updateTotalTravellers();

    numAdultsInput.addEventListener("change", updateTotalTravellers);
    numChildrenInput.addEventListener("change", updateTotalTravellers);

    document.addEventListener("click", (event) => {
      if (!travellersInput.contains(event.target) && !travellersDropdown.contains(event.target)) {
        travellersDropdown.style.display = 'none';
      }
    });
  },
  renderHotels(hotels = []) {
    const dropdown = document.getElementById('hotel_dropdown');
    const hotelIdInput = document.getElementById('hotel_id');
    const inputField = document.getElementById('selected_hotel');
    dropdown.innerHTML = '';

    // Get hotel_id from the URL
    const urlParts = window.location.pathname.split('/');
    const currentHotelId = parseInt(urlParts[urlParts.length - 1]) || 0;

    // Filter hotels to show only the selected one if a hotel_id is present
    let filteredHotels = hotels;
    if (currentHotelId) {
        filteredHotels = hotels.filter(hotel => hotel.id === currentHotelId);
    } else {
        filteredHotels.unshift({ id: 0, name: 'ALL' });
    }

    filteredHotels.forEach(hotel => {
        const hotelItem = document.createElement('div');
        hotelItem.classList.add('dropdown-item');
        hotelItem.setAttribute('data-hotel-id', hotel.id);

        if (hotel.id === currentHotelId || currentHotelId === 0) {
            hotelItem.classList.add('selected');
            hotelIdInput.value = hotel.id;
            inputField.value = hotel.name;
        }

        let hotelContent = '';
        if (hotel.name) hotelContent += `<span class="hotel-name">${hotel.name}</span>`;
        if (hotel.address) hotelContent += `<span class="hotel-address">${hotel.address}</span>`;

        hotelItem.innerHTML = hotelContent;
        hotelItem.addEventListener('click', () => {
            hotelIdInput.value = hotel.id;
            inputField.value = hotel.name;
            dropdown.classList.remove('show');
        });
        dropdown.appendChild(hotelItem);
    });

    // Show the dropdown when input is clicked
    inputField.addEventListener('click', () => {
        dropdown.classList.toggle('show');
    });

    // Close dropdown if clicking outside
    document.addEventListener('click', (event) => {
        if (!dropdown.contains(event.target) && event.target !== inputField) {
            dropdown.classList.remove('show');
        }
    });
  }
});

// Multi-Hotel Widget
publicWidget.registry.HotelSwitchWidget = publicWidget.Widget.extend({
  selector: '#multi_hotel_container',
  disabledInEditableMode: false,

  /**
   * @override
   */
  init: function (parent, options) {
    return this._super.apply(this, arguments);
  },
  /**
   * @override
   */
  start: async function () {
    const def = this._super.apply(this, arguments);
    this.orm = this.bindService('orm')
    const self = this;
    await jsonrpc(
      '/wk/get_hotels',
      {},
    ).then(function (hotels) {
      if (hotels.length)
        self._renderHotelsData(hotels);
    });
    return def;
  },
  _renderHotelsData: function (data) {
    const $container = this.$el.find('.mh-card-box');
    $container.empty()
    data.forEach((hotel) => {
      const hotelCard = renderToFragment(
        "hotel_management_system.multi-hotel-card-template",
        {
          hotel: hotel,
        }
      );
      $container.append(hotelCard);
    });
  },
  _clearContent: function () {
    const $templateArea = this.$el.find('.mh-card-box');
    this.trigger_up('widgets_stop_request', {
      $target: $templateArea,
    });
    $templateArea.html('');
  },
  destroy: function () {
    this._clearContent(); 
    this._super.apply(this, arguments);
  },
});
