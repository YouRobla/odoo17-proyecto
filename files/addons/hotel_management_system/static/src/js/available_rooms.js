/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */
import { jsonrpc } from "@web/core/network/rpc_service";
import publicWidget from "@web/legacy/js/public/public_widget";
import '@website_sale/js/website_sale';

var today = new Date();
var dd = String(today.getDate()).padStart(2, '0');
var mm = String(today.getMonth() + 1).padStart(2, '0');
var yyyy = today.getFullYear();
today = yyyy + '-' + mm + '-' + dd;

$(".wk_check_in").prop("min", today);

$('.wk_check_out').on('click', function () {
    if ($(".wk_check_in").val()) {
        var check_in_val = $(".wk_check_in").val();
        var currentCheckin = new Date(check_in_val);
        currentCheckin.setDate(currentCheckin.getDate() + 1);
        var formatted_checkoutDate = JSON.stringify(currentCheckin);
        $(this).prop("min", formatted_checkoutDate.slice(1, 11));
    }
});

$("#check_in_cart").prop("min", today);

$('#check_in_cart').on('change', function () {
    if (Date.parse($("#check_in_cart").val()) >= Date.parse($("#check_out_cart").val())) {
        $("#check_out_cart").val(null);
    }
});

$('#check_out_cart').on('click', function () {
    if ($("#check_in_cart").val()) {
        var check_in_val = $("#check_in_cart").val();
        var currentCheckin = new Date(check_in_val);
        currentCheckin.setDate(currentCheckin.getDate() + 1);
        var formatted_checkoutDate = JSON.stringify(currentCheckin);
        $(this).prop("min", formatted_checkoutDate.slice(1, 11));
    }
});

$(document).ready(function () {
    $('.add_Guest_span').on('click', function () {
        $('#addguestModalCenter').modal('show');
        var table_id = $(this).parent('div').parent('div').children('table').attr('id');

        $('.table_id_store').val(table_id);
    })
    $('.addGuestModal_button').on('click', function () {
        var fullName = $('.fullName').val();
        var genderValue = $("input[name='genderinlineRadioOptions']:checked").val();
        var age = $('.age').val();
        var table_id_store = $('.table_id_store').val();
        if (fullName && genderValue && age && table_id_store) {
            // var tableid = $('#' + table_id_store);
            var desire_table = $('#accordionGuest').find("table#" + table_id_store);
            var tbody_val = desire_table.children('tbody');
            var tbody_div = tbody_val.first();
            var select_option;
            if (genderValue == "male") {
                select_option = '<option value="male" selected>Male</option><option value="female">Female</option>option value="other">Other</option>';
            }
            else if (genderValue == "female") {
                select_option = '<option value="male">Male</option><option value="female" selected>Female</option>option value="other">Other</option>';
            }
            else {
                select_option = '<option value="male">Male</option><option value="female">Female</option><option value="other" selected>Other</option>';
            }

            tbody_div.append(`<tr>
            <td>
            <input class = "form-control" type="text" name="name" value=`+ fullName + ` required="True"/>
    </td>
    <td>
    <select class = "form-control" name="gender" id="gender" required="True">
    `+ select_option + `
    </select>
    </td>
    <td>
    <input class = "form-control" type="number" value=`+ age + ` name="age" required="True"/>
    </td>
    <td>
    <span type="button" id="remove_row" class="btn mt-2 mb-2 btn-danger btn-sm inline remove_row">Remove</span>
    </td>
    </tr>`);
            $('#addguestModalCenter').modal('hide');
        }
    })
    $('.guest_info_body').on('click', '.remove_row', function () {
        var tbody_val = $(this).parent('td').parent('tr').parent('tbody');
        if (tbody_val.children('tr').length > 1) {
            $(this).closest('tr').remove();
        }
    });
    $('#wk_check_in').on('change', function () {
        if (Date.parse($("#wk_check_in").val()) >= Date.parse($("#wk_check_out").val())) {
            $("#wk_check_out").val(null);
        }
    });
    $('#submit_detail').on('click', function () {
        var info_dict = {};


        var check_point = 0;
        $('.outer_div').each(function () {
            var max_child = 0;
            var max_adult = 0;
            var total_adult = 0;
            var total_child = 0;
            var line_id = $(this).attr('id');
            max_adult = $(this).find('.max_adult').val();
            max_child = $(this).find('.max_child').val();
            var data_list = [];
            $(this).children('table').children('tbody').find('tr').each(function (i, el) {

                var $tds = $(this).find("td");

                var dict = {};
                $tds.each(function (j, val) {
                    if ($(this).children().attr('type') == "number") {
                        if ($(this).children().val() < 0) {
                            check_point = 3;
                        }
                        if ($(this).children().val() >= 18) {
                            total_adult += 1;
                        }
                        else {
                            total_child += 1;
                        }
                    }
                    if (!$(this).children().val() && !($(this).children().attr('type') == "button")) {
                        check_point = 1
                        $("#data_missing").css("display", "none");
                        $('#data_missing').css("display", "block");
                    }
                    else {
                        if (!($(this).children().attr('type') == "button")) {
                            dict[$(this).children().attr('name')] = $(this).children().val();
                        }

                    }

                });
                if (max_adult < total_adult || max_child < total_child) {
                    check_point = 2
                }
                data_list.push(dict);
            });
            info_dict[line_id] = data_list;
        });
        if (check_point == 2) {
            $("#acceptable_guest").css("display", "none");
            $('#acceptable_guest').css("display", "block");

        }
        else if (check_point == 3) {
            $("#correct_age").css("display", "none");
            $('#correct_age').css("display", "block");

        }
        else if (check_point == 0) {
            jsonrpc('/guest/info', { guest_detail: info_dict }).then(function (val) {
                window.location = '/shop/checkout?express=1';
            });

        }

    });
});

$('.emptyCart').on('click', function () {
    jsonrpc('/empty/cart').then(function () {
        $('#modalAbandonedCart').modal('hide');
    });
});

$(document).on('click', '#check_booking_room_availability', function () {
    if ($('#check_in_cart').val() && $('#check_out_cart').val()) {
        $("#caution_date").css("display", "none");
        var hotel_id = $('#prod_hotel_id').val();
        var check_in = $('#check_in_cart').val();
        var check_out = $('#check_out_cart').val();
        var product_template_id = $('input[name="product_template_id"]').val();
        var product_id = $('input[name="product_id"]').val();
        var des_att_value = $(".no_variant:checked").attr('data-attribute_name');
        var des_value = $(".no_variant:checked").attr('data-value_name');
        var requirement_qty = $('input[name="add_qty"]').val() || 1;
        var value = '';
        if (des_att_value && des_value) {
            value = des_att_value + ":" + des_value
        }
        jsonrpc('/available/qty/details', {
            hotel_id: hotel_id,
            check_in: check_in,
            check_out: check_out,
            product_template_id: product_template_id,
            product_id: product_id,
            requirement_qty: requirement_qty,
            availabilty_check: '0',
            order_des: value
        }).then(function (val) {

            if (val['result'] == 'fail') {
                if (val['msg'] == ' ') {
                    $(".msg_alert").css("display", "none");
                    $("#caution_msg").css("display", "block");
                }
                else {
                    $(".msg_alert").css("display", "none");
                    $("#caution_msg").css("display", "block");
                    $("#caution_msg").text(val['msg']);
                }
            }
            else if (val['result'] == 'unmatched') {
                $('#modalAbandonedCart').find('.warn-msg').text(val['msg']);
                if (val['both']) $('.warn-rm-msg').show();
                else $('.warn-rm-msg').hide();
                $('#modalAbandonedCart').modal('show');
            }
            else {
                // $("#available_room").css("display", "none");
                $(".msg_alert").css("display", "none");
                $("#success_msg").css("display", "block");
                setTimeout(function () { window.location = '/shop/cart'; }, 1000);
            }
        });
    }
    else {
        $(".msg_alert").css("display", "none");
        $("#caution_date").css("display", "block");
    }
});

publicWidget.registry.WebsiteSale.include({
    events: Object.assign(publicWidget.registry.WebsiteSale.prototype.events, {
        'change #check_in_cart': '_onchangecheck_in_out_cart',
        'change #check_out_cart': '_onchangecheck_in_out_cart',
    }),
    _onchangecheck_in_out_cart: function () {
        $("input[name='add_qty']").trigger('change');
    },
    _getOptionalCombinationInfoParam: function () {
        var self = this;
        var check_in = self.$el.find('#check_in_cart').val();
        var check_out = self.$el.find('#check_out_cart').val();
        if (check_in && check_out) {
            const check_in_date = new Date(check_in);
            const check_out_date = new Date(check_out);
            const diff_time = Math.abs(check_out_date - check_in_date);
            const days = Math.ceil(diff_time / (1000 * 60 * 60 * 24));
            return {
                days_count: days
            };
        }
    },
});

document.querySelectorAll(".hotel-menu a").forEach(anchor => {
    anchor.addEventListener("click", function (e) {
        e.preventDefault();

        document.querySelectorAll(".hotel-menu a").forEach(link => {
            link.classList.remove("active-underline");
        });

        // Add underline to the clicked link
        this.classList.add("active-underline");

        const targetId = this.getAttribute("href").substring(1);
        const targetElement = document.getElementById(targetId);
        if (targetElement) {
            window.scrollTo({
                top: targetElement.offsetTop - 50,
                behavior: "smooth"
            });
        }
    });
});
