/** @odoo-module **/
/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
/* License URL : <https://store.webkul.com/license.html/> */

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useState, onWillUpdateProps, onPatched, onWillStart, onWillUnmount } from "@odoo/owl";

export class HotelChart extends Component {
    static template = "HotelChart";
    static props = {
        'id': String,
        'type': String,
        'chartData': { type: Array, optional: true, default: [] },
        'index': Number,
    };

    setup() {
        this.chart = null;
        onWillUpdateProps((nextProps) => {
            if (
                nextProps.chartData !== this.props.chartData ||
                nextProps.type !== this.props.type
            ) this._renderChart(nextProps.id, nextProps.type, nextProps.chartData, nextProps.index);
        });

        onMounted(() => {
            this._renderChart(this.props.id, this.props.type, this.props.chartData, this.props.index);
        });

        onWillUnmount(() => {
            if (this.chart) this.chart.dispose();
        });
    }
    _renderChart(chartId, chartType, chartData, index) {
        const chartsContainer = document.querySelectorAll('.booking-chart')[index];

        if (!chartsContainer) {
            console.error('Charts container not found');
            return;
        }

        chartsContainer.innerHTML = '';
        const uniqueChartId = `${chartId}_${new Date().getTime()}`;
        const chartDiv = document.createElement('div');
        chartDiv.id = uniqueChartId;
        chartDiv.style.width = '100%';
        chartDiv.style.height = '400px';
        chartsContainer.appendChild(chartDiv);

        if (this.chartRoot) {
            this.chartRoot.dispose();
            this.chartRoot = null;
        }

        let root = am5.Root.new(uniqueChartId);
        root.setThemes([am5themes_Animated.new(root)]);

        let chart;
        if (chartType === "map") {
            chart = this._createMapChart(root, chartData);
        } else if (chartType === "line") {
            chart = this._createLineChart(root, chartData);
        } else if (chartType === "bar") {
            chart = this._createBarChart(root, chartData);
        } else if (chartType === "pie") {
            chart = this._createPieChart(root, chartData);
        } else if (chartType === "customer") {
            chart = this.renderTopPartnersChart(root, chartData);
        } else {
            console.error(`Unsupported chart type: ${chartType}`);
            return;
        }

        chart.appear(500, 80);
    }
    _createLineChart(root, data) {
        data = this._prepareData(data);
        let chart = root.container.children.push(
            am5xy.XYChart.new(root, {
                focusable: true,
                panX: true,
                panY: true,
                wheelX: "panX",
                wheelY: "zoomX",
            })
        );

        let xAxis = chart.xAxes.push(
            am5xy.DateAxis.new(root, {
                maxDeviation: 0.1,
                groupData: false,
                baseInterval: { timeUnit: "day", count: 1 }, // Adjust to "month" if data spans months
                renderer: am5xy.AxisRendererX.new(root, { minGridDistance: 50 }),
                tooltip: am5.Tooltip.new(root, {}),
            })
        );

        let yAxis = chart.yAxes.push(
            am5xy.ValueAxis.new(root, {
                maxDeviation: 0.1,
                renderer: am5xy.AxisRendererY.new(root, {}),
            })
        );

        let series = chart.series.push(
            am5xy.LineSeries.new(root, {
                minBulletDistance: 10,
                xAxis: xAxis,
                yAxis: yAxis,
                valueYField: "value",
                valueXField: "categ",
                tooltip: am5.Tooltip.new(root, {
                    pointerOrientation: "horizontal",
                    labelText: "{value}",
                }),
            })
        );

        series.strokes.template.setAll({
            strokeWidth: 3,
        });

        series.data.setAll(data);
        chart.set("cursor", am5xy.XYCursor.new(root, { xAxis: xAxis }));
        return chart;
    }
    _createBarChart(root, data) {
        data = this._prepareData(data);

        let chart = root.container.children.push(
            am5xy.XYChart.new(root, {
                focusable: true,
                panX: true,
                panY: true,
                wheelX: "panX",
                wheelY: "zoomX",
            })
        );

        let xAxis = chart.xAxes.push(
            am5xy.DateAxis.new(root, {
                maxDeviation: 0.1,
                groupData: false,
                baseInterval: { timeUnit: "day", count: 1 }, // Adjust to "month" if data spans months
                renderer: am5xy.AxisRendererX.new(root, { minGridDistance: 50 }),
                tooltip: am5.Tooltip.new(root, {}),
            })
        );

        let yAxis = chart.yAxes.push(
            am5xy.ValueAxis.new(root, {
                maxDeviation: 0.1,
                renderer: am5xy.AxisRendererY.new(root, {}),
            })
        );

        let series = chart.series.push(
            am5xy.ColumnSeries.new(root, {
                xAxis: xAxis,
                yAxis: yAxis,
                valueYField: "value",
                valueXField: "categ",
                tooltip: am5.Tooltip.new(root, {
                    labelText: "{value}",
                }),
            })
        );

        series.columns.template.setAll({
            cornerRadiusTL: 5,
            cornerRadiusTR: 5,
            strokeOpacity: 0,
        });

        series.data.setAll(data);

        chart.set("cursor", am5xy.XYCursor.new(root, { xAxis: xAxis }));
        return chart;
    }
    _createPieChart(root, data) {
        let chart = root.container.children.push(am5percent.PieChart.new(root, {
            layout: root.verticalLayout,
            radius: am5.percent(100),
            paddingBottom: 50,
            paddingTop: 40,
            paddingLeft: 0,
            paddingRight: 0
        }));

        let series = chart.series.push(
            am5percent.PieSeries.new(root, {
                valueField: "value",
                categoryField: "categ",
                tooltip: am5.Tooltip.new(root, {
                    labelText: "{categ}: {value}",
                }),
            })
        );

        series.data.setAll(data);
        return chart;
    }
    _prepareData(data) {
        if (data) {
            let transformedData = data.map(item => ({
                ...item,
                categ: !isNaN(Date.parse(item.categ)) ? new Date(item.categ).getTime() : item.categ // Check if categ is a valid date string
            }));

            return transformedData;
        }
    }
    _createMapChart(root, data) {
        let chart = root.container.children.push(
            am5map.MapChart.new(root, {
                panX: "rotateX",
                panY: "translateY",
                projection: am5map.geoMercator(),
            })
        );

        var zoomControl = chart.set("zoomControl", am5map.ZoomControl.new(root, {}));
        zoomControl.homeButton.set("visible", true);

        // Create main polygon series for countries
        var polygonSeries = chart.series.push(
            am5map.MapPolygonSeries.new(root, {
                geoJSON: am5geodata_worldLow,
                exclude: ["AQ"],
            })
        );

        polygonSeries.mapPolygons.template.setAll({
            fill: am5.color(0xdadada),
        });

        // Create point series for markers
        var pointSeries = chart.series.push(am5map.ClusteredPointSeries.new(root, {}));

        // Create regular bullets
        pointSeries.bullets.push(function (root, series, dataItem) {
            var circle = am5.Circle.new(root, {
                radius: 6,
                tooltipY: 0,
                fill: am5.color(0xff8c00),
                tooltipText: "{title}",
            });

            return am5.Bullet.new(root, {
                sprite: circle,
            });
        });

        // Set the data
        const locations = data.map((item) => ({
            title: item.city,
            latitude: item.latitude,
            longitude: item.longitude,
        }));
        pointSeries.data.setAll(locations);
        return chart
    }
    renderTopPartnersChart(root, data) {
        let chart = root.container.children.push(
            am5xy.XYChart.new(root, {
                panX: false,
                panY: false,
                wheelX: "none",
                wheelY: "none",
                paddingBottom: 50,
                paddingTop: 40,
                paddingLeft: 0,
                paddingRight: 0
            })
        );

        var xRenderer = am5xy.AxisRendererX.new(root, {
            minGridDistance: 60,
            minorGridEnabled: true
        });
        xRenderer.grid.template.set("visible", false);

        var xAxis = chart.xAxes.push(
            am5xy.CategoryAxis.new(root, {
                paddingTop: 40,
                categoryField: "name",
                renderer: xRenderer,
                tooltip: am5.Tooltip.new(root, {
                    labelText: "{name}"
                })
            })
        );

        var yRenderer = am5xy.AxisRendererY.new(root, {});
        yRenderer.grid.template.set("strokeDasharray", [3]);

        var yAxis = chart.yAxes.push(
            am5xy.ValueAxis.new(root, {
                min: 0,
                renderer: yRenderer
            })
        );

        // Add series
        var series = chart.series.push(
            am5xy.ColumnSeries.new(root, {
                name: "Bookings",
                xAxis: xAxis,
                yAxis: yAxis,
                valueYField: "steps",
                categoryXField: "name",
                sequencedInterpolation: true,
                calculateAggregates: true,
                maskBullets: false,
                tooltip: am5.Tooltip.new(root, {
                    dy: -30,
                    pointerOrientation: "vertical",
                    labelText: "{valueY}"
                })
            })
        );

        series.columns.template.setAll({
            strokeOpacity: 0,
            cornerRadiusBR: 10,
            cornerRadiusTR: 10,
            maxWidth: 50,
            fillOpacity: 0.8
        });

        var circleTemplate = am5.Template.new({});

        // Add images and animate on hover
        series.bullets.push(function (root, series, dataItem) {
            var bulletContainer = am5.Container.new(root, {});
            var circle = bulletContainer.children.push(
                am5.Circle.new(root, { radius: 34 }, circleTemplate)
            );

            var maskCircle = bulletContainer.children.push(
                am5.Circle.new(root, { radius: 27 })
            );

            var imageContainer = bulletContainer.children.push(
                am5.Container.new(root, { mask: maskCircle })
            );

            var image = imageContainer.children.push(
                am5.Picture.new(root, {
                    templateField: "pictureSettings",
                    centerX: am5.p50,
                    centerY: am5.p50,
                    width: 60,
                    height: 60
                })
            );

            // Create a bullet with the image and circle
            var bullet = am5.Bullet.new(root, {
                locationY: 0,  // Initial position of the image at the bottom
                sprite: bulletContainer
            });

            // Hover effect: Animate the image position on hover
            // bulletContainer.events.on("pointerover", function () {
            //     bullet.animate({
            //         key: "locationY",
            //         to: 1,  // Move to the top of the column
            //         duration: 100,
            //         easing: am5.ease.out(am5.ease.cubic)
            //     });
            // });

            // bulletContainer.events.on("pointerout", function () {
            //     bullet.animate({
            //         key: "locationY",
            //         to: 0,  // Move back to the bottom
            //         duration: 100,
            //         easing: am5.ease.out(am5.ease.cubic)
            //     });
            // });
            var currentlyHovered;

            series.columns.template.events.on("pointerover", function (e) {
                handleHover(e.target.dataItem);
            });

            series.columns.template.events.on("pointerout", function (e) {
                handleOut();
            });

            function handleHover(dataItem) {
                if (dataItem && currentlyHovered != dataItem) {
                    handleOut();
                    currentlyHovered = dataItem;
                    var bullet = dataItem.bullets[0];
                    bullet.animate({
                        key: "locationY",
                        to: 1,
                        duration: 600,
                        easing: am5.ease.out(am5.ease.cubic)
                    });
                }
            }

            function handleOut() {
                if (currentlyHovered) {
                    var bullet = currentlyHovered.bullets[0];
                    bullet.animate({
                        key: "locationY",
                        to: 0,
                        duration: 600,
                        easing: am5.ease.out(am5.ease.cubic)
                    });
                }
            }
            return bullet;
        });

        // Heat rules
        series.set("heatRules", [
            {
                dataField: "valueY",
                min: am5.color(0xe5dc36),
                max: am5.color(0x5faa46),
                target: series.columns.template,
                key: "fill"
            },
            {
                dataField: "valueY",
                min: am5.color(0xe5dc36),
                max: am5.color(0x5faa46),
                target: circleTemplate,
                key: "fill"
            }
        ]);

        // Set data
        series.data.setAll(data);
        xAxis.data.setAll(data);

        // Add cursor
        var cursor = chart.set("cursor", am5xy.XYCursor.new(root, {}));
        cursor.lineX.set("visible", false);
        cursor.lineY.set("visible", false);

        // Animate series on load
        series.appear();
        return chart;
    }
}

export class HotelDashboard extends Component {
    static components = { HotelChart };

    async setup() {
        let self = this;
        this.orm = useService("orm");
        this.action = useService("action");
        let user = useService("user");

        this.partnerId = user.partnerId;
        this.state = useState({
            hotel: "0",
            period: "2",
            periodName: 'Last 30 Days',
            kpis: {},
            charts: [
                { id: "location", type: "map", title: "Location", dataKey: "location", index: 0 },
                { id: "top_customers", type: "customer", title: "Top Customers", dataKey: "top_customers", index: 1 },
                { id: "bookingsChart", type: "pie", title: "Bookings vs Cancellations", dataKey: "bookings_datewise", index: 2 },
                { id: "sourceChart", type: "pie", title: "Booking Source", dataKey: "booking_sources", index: 3 },
                { id: "revenueChart", type: "bar", title: "Revenue", dataKey: "revenue_datewise", index: 4 },
                { id: "bookingCountDatewise", type: "line", title: "Bookings", dataKey: "bookings_count", index: 5 },
            ],
        });
        this.nameMapping = {
            "1": 'Last 7 Days',
            "2": 'Last 30 Days',
            "3": 'Last 90 Days',
            "4": 'Last 180 Days',
            "5": 'Last 365 Days',
            "6": 'Last 3 years',
        }
        onWillStart(() => this._fetchDashboardData());
        onMounted(() => {
            function updateClock() {
                if (document.getElementById('clock')) document.getElementById('clock').innerHTML = luxon.DateTime.now().toFormat("yyyy-MM-dd HH:mm:ss");
            }
            updateClock();
            setInterval(updateClock, 1000);
        });
    }
    async _fetchDashboardData() {
        const periodMapping = {
            "1": 7,
            "2": 30,
            "3": 90,
            "4": 180,
            "5": 365,
            "6": 1095,
        }

        const days = periodMapping[this.state.period];
        const startDate = new Date(new Date().setDate(new Date().getDate() - days));

        const data = await this.orm.call("hotel.booking", "get_dashboard_data", ['',
            startDate.toISOString(),
            parseInt(this.state.hotel)
        ]);
        this.updateState(data);
    }
    updateState(data) {
        this.state.hotels = data['hotels'];
        this.state.rooms = data['rooms'];
        this.currency = data['currency_symbol'];
        const bookings = data['bookings'];
        let revenue = 0;
        let cancellations = 0;
        let pendingCheckins = 0;
        let pendingCheckouts = 0;
        let ongoingBookings = 0;
        let pendingCheckinList = [];
        let pendingCheckoutList = [];
        let ongoingBookingsList = [];
        let cancelledBooking_ids = [];

        const today = new Date().toISOString().split('T')[0];

        const revenueDatewise = {};
        const bookVsCancel = { booked: 0, canceled: 0 };
        const bookingCountDatewise = {};
        const bookingSources = { website: 0, manual: 0, agent: 0 };

        bookings.forEach((booking) => {
            const bookingDate = booking.check_in.split(' ')[0];

            // Count booking sources
            if (booking.booking_reference === "sale_order") {
                bookingSources.website++;
            } else if (booking.booking_reference === "manual") {
                bookingSources.manual++;
            }
            else if (booking.booking_reference === "agent") {
                bookingSources.agent++;
            }

            if (booking.status_bar === "cancel") {
                cancelledBooking_ids.push(booking.id)
                cancellations++;
                bookVsCancel.canceled++;
            } else {
                if (!['draft', 'cancel'].includes(booking.status_bar)) {
                    revenue += booking.total_amount;

                    if (!revenueDatewise[bookingDate]) {
                        revenueDatewise[bookingDate] = 0;
                    }
                    revenueDatewise[bookingDate] += booking.total_amount;
                    if (!bookingCountDatewise[bookingDate]) {
                        bookingCountDatewise[bookingDate] = 0;
                    }
                    bookingCountDatewise[bookingDate]++;
                }
                bookVsCancel.booked++;
                if (booking.check_in >= today && booking.status_bar == "confirm") {
                    pendingCheckinList.push(booking.id);
                    pendingCheckins++;
                }
                if (booking.check_out >= today && ['allot'].includes(booking.status_bar)) {
                    pendingCheckoutList.push(booking.id)
                    pendingCheckouts++;
                }
                if (['confirm', 'allot'].includes(booking.status_bar)) {
                    ongoingBookingsList.push(booking.id)
                    ongoingBookings++;
                }
            }
        });

        this.state.kpis = {
            // total_revenue: `${this.currency}${revenue.toFixed(2)}`,
            total_bookings: bookings.length,
            canceled_bookings: cancellations,
            // occupancy_rate: (ongoingBookings / bookings.length * 100).toFixed(2),
            pending_checkins: pendingCheckins,
            pending_checkouts: pendingCheckouts,
            ongoing_bookings: ongoingBookings,
            pendingCheckinList: pendingCheckinList,
            pendingCheckoutList: pendingCheckoutList,
            ongoingBookingsList: ongoingBookingsList,
            cancelledBooking_ids: cancelledBooking_ids
        };

        if(revenue) this.state.kpis['total_revenue'] = `${this.currency}${revenue.toFixed(2)}`
        if(ongoingBookings && bookings.length) this.state.kpis['occupancy_rate'] = (ongoingBookings / bookings.length * 100).toFixed(2)

        const revenueData = data?.revenue || {};
        const currency = this.currency || '';
        
        ['today', 'yesterday', 'last_week'].forEach((key) => {
            const value = revenueData[key];
            this.state[`${key}_revenue`] = `${currency}${value ? value.toFixed(2) : '0.0'}`;
        });
        
        this.state.booking_ids = data?.booking_ids || [];
        
        const todayRevenue = revenueData.today || 0;
        const yesterdayRevenue = revenueData.yesterday || 0;
        
        this.state.revenue_percent = yesterdayRevenue > 0
            ? ((todayRevenue / yesterdayRevenue) * 100).toFixed(2)
            : '0';

        this.state.chartData = {
            revenue_datewise: Object.keys(revenueDatewise).map((date) => ({
                categ: date,
                value: revenueDatewise[date],
            })),
            bookings_datewise: [
                { categ: "Booked", value: bookVsCancel.booked },
                { categ: "Canceled", value: bookVsCancel.canceled },
            ],
            bookings_count: Object.keys(bookingCountDatewise).map((date) => ({
                categ: date,
                value: bookingCountDatewise[date],
            })),
            booking_sources: [
                { categ: "Website", value: bookingSources.website },
                { categ: "Direct", value: bookingSources.manual },
                { categ: "Via Agent", value: bookingSources.agent },
            ],
            location: data['map_data'],
            top_customers: data['top_customers'],
        };
    }
    getChartProps(chart) {
        return {
            id: chart.id,
            index: chart.index,
            type: chart.type,
            chartData: this.state.chartData[chart.dataKey],
        }
    }
    async _onSelectPeriod(ev) {
        this.state.period = ev.target.value;
        this.state.periodName = this.nameMapping[this.state.period];
        await this._fetchDashboardData();
    }
    _onChartTypeChange(ev, chartId) {
        const newType = ev.target.value;
        const updatedCharts = this.state.charts.map((chart) => {
            if (chart.id === chartId) chart.type = newType;
            return chart;
        });
        this.state.charts = updatedCharts;
    }
    openRoom(id) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: _t('Hotel Room'),
            target: 'new',
            res_id: id,
            res_model: 'product.template',
            views: [[false, 'form']],
            context: { edit: false, create: false },
        });
    }
    OnclickContainer(ev) {
        ev.stopPropagation();
        let roomTypeDomain = [];
        let group = [];

        // @class {total_available_room} adding a domain to filter unbooked room.
        // @class {total_booked} adding a domain to filter booked room.

        if (ev.target.classList.contains('cancellation')) {
            roomTypeDomain.push(["id", "in", this.state.kpis.cancelledBooking_ids]);
            // if (this.productData.available_rooms) group.push('product_tmpl_id');
        }
        else if (ev.target.classList.contains('total_booking')) {
            roomTypeDomain.push(["id", "in", this.state.booking_ids]);
            // if (this.bookedData.length) group.push('id');
        }
        else if (ev.target.classList.contains('current_bookings')) {
            roomTypeDomain.push(["id", "in", this.state.kpis.ongoingBookingsList]);
            // if (this.bookedData.length) group.push('id');
        }
        else if (ev.target.classList.contains('revenue')) {
            roomTypeDomain.push(["id", "in", this.state.booking_ids]);
            if (this.state.booking_ids.length) group.push('total_amount');
        }
        else if (ev.target.classList.contains('pending_checkins')) {
            roomTypeDomain.push(["id", "in", this.state.kpis.pendingCheckinList]);
            // if (this.bookedData.length) group.push('id');
        }
        else if (ev.target.classList.contains('pending_checkouts')) {
            roomTypeDomain.push(["id", "in", this.state.kpis.pendingCheckoutList]);
            // if (this.bookedData.length) group.push('id');
        }
        const classesToCheck = ['cancellation', 'total_booking', 'current_bookings', 'pending_checkins', 'pending_checkouts', 'revenue'];
        const hasAnyClass = classesToCheck.some(cls => ev.target.classList.contains(cls));
        if (ev.target.getAttribute('count') != 0 && hasAnyClass) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: 'hotel.booking',
                name: 'Bookings',
                views: [[false, 'tree'], [false, 'form']],
                domain: roomTypeDomain,
                res_id: false,
                context: {
                    group_by: group,
                    create: true,
                },
            }, {
                additionalContext: this.props.context,
            });
        }


    }
    async _onChangeHotel(ev){
        this.state.hotel = ev.target.value;
        await this._fetchDashboardData();
    }
}
HotelDashboard.template = "hotel_dashboard_action";
registry.category("actions").add("hotel_dashboard_action", HotelDashboard);
export default HotelDashboard;
