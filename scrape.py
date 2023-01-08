
import scrapy
import datetime
import time

class CraigsListSpider(scrapy.Spider):
    name = 'craigslist'

    custom_settings = {
        # 0.5s download delay
        'DOWNLOAD_DELAY': 2.0
    }

    # build url

    search_terms = ['https://vancouver.craigslist.org/search/apa?sort=date']
    search_terms.append('hasPic=1')
    search_terms.append('min_price=3700')
    search_terms.append('max_price=5700')
    search_terms.append('min_bedrooms=3')
    search_terms.append('max_bedrooms=5')
    search_terms.append('min_bathrooms=2')
    search_terms.append('minSqft=1500')
    search_terms.append('housing_type=3') # cottage/cabin
    search_terms.append('housing_type=4') # duplex (two units in one building)
    search_terms.append('housing_type=6') # house
    search_terms.append('housing_type=7') # in-law (often laneway houses)
    search_terms.append('housing_type=9') # townhouse

    url = '&'.join(search_terms)

    start_urls = []

    # there is no is_unfurnished term, so search twice, once with furnished=1 and once without
    # and subtract the furnished homes from the without list using ids

    # for i in [0]:
    for i in (0, 100, 200, 300, 400):
        start_urls.append('%s&s=%s' % (url, i))
        start_urls.append('%s&s=%s&is_furnished=1' % (url, i))

    furnished_responses = []
    unfurnished_responses = []

    items = 0

    index_file = None
    furnished = []
    locations = dict()
    repost = []

    def parse(self, response):
        if response.url.endswith('is_furnished=1'):
            self.furnished_responses.append(response)
        else:
            self.unfurnished_responses.append(response)
            for sel in response.xpath('//li[@class="result-row"]'):
                url = sel.xpath('.//a/@href').extract()[0]
                location_request = scrapy.Request(url,
                                        callback=self.process_location)
                time.sleep(1)
                yield location_request

    def process_location(self, response):
        if response.xpath("//*[contains(text(), 'var repost_of')]"):
            self.repost.append(response.url)
        # extract latitude and longitude from nested page and key by url
        try:
            latitude = response.xpath('//div[@id="map"]/@data-latitude').extract()[0]
            longitude = response.xpath('//div[@id="map"]/@data-longitude').extract()[0]
            date = response.xpath('.//time[@class="date timeago"]/text()')[0].extract()
            date = ' '.join(date.split())
            self.locations[response.url] = (latitude, longitude, date)
        except IndexError:
            pass

    def process_furnished(self, responses):
        for response in responses:
            # find and store all ids for all furnished properties
            for sel in response.xpath('//div[@class="result-info"]'):
                id = sel.xpath('.//a[@class="result-title hdrlnk"]/@data-id').extract()[0]
                self.furnished.append(id)

    def process_unfurnished(self, responses):

        unsorted_entries = dict()

        processed_ids = []

        for response in responses:

            # region 1 = ubc / point grey / dunbar
            # region 2 = kits / kerrisdale / south granville / mount pleasant
            # region 3 = eastside
            # region 4 = north vancouver
            # region 5 = west vancouver
            # region 6 = downtown

            location_regions = []
            location_regions.append((49.29, -123.3, 49.2, -123.177, 1))
            location_regions.append((49.296, -123.095, 49.229, -123.0357, 3))
            location_regions.append((49.27049, -123.177, 49.2, -123.076, 2))
            location_regions.append((49.279, -123.177, 49.27049, -123.1388, 2))
            location_regions.append((49.2759, -123.1388, 49.27049, -123.1324, 2))
            location_regions.append((49.27266, -123.11738, 49.27049, -123.095, 2))
            # location_regions.append((49.4, -123.129, 49.295, -122.93, 4))
            # location_regions.append((49.4, -123.3, 49.298, -123.129, 5))
            # location_regions.append((49.31, -123.17, 49.26, -123.09, 6))

            for sel in response.xpath('//div[@class="result-info"]'):
                id = sel.xpath('.//a[@class="result-title hdrlnk"]/@data-id').extract()[0]
                # ignore furnished or duplicate ids
                if id in self.furnished or id in processed_ids:
                    continue
                processed_ids.append(id)

                url = sel.xpath('.//a[@class="result-title hdrlnk"]/@href').extract()[0]
                title = sel.xpath('.//a[@class="result-title hdrlnk"]/text()').extract()[0]
                # remove non-ascii characters
                try:
                    title.encode('ascii')
                except UnicodeEncodeError:
                    continue

                # ignore reposts
                if url in self.repost:
                    continue

                meta = sel.xpath('.//span[@class="result-meta"]')
                price = meta.xpath('.//span[@class="result-price"]/text()').extract()[0]
                details = meta.xpath('.//span[@class="housing"]/text()').extract()[0]
                details = details.split()
                bedroom = details[0][:-2]
                area = details[2][:-2]

                time = sel.xpath('.//time[@class="result-date"]/@datetime')[0].extract()
                time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
                latitude = 0
                longitude = 0

                region = None

                if url in self.locations:
                    (latitude, longitude, date) = self.locations[url]
                    latitude = float(latitude)
                    longitude = float(longitude)

                    for (lat1, long1, lat2, long2, region_id) in location_regions:
                        if latitude <= lat1 and latitude > lat2 and longitude >= long1 and longitude < long2:
                            region = region_id
                            break

                    time = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M")

                now = datetime.datetime.now()
                seconds = (now - time).total_seconds()
                # ignore if posting is older than three days
                if seconds > 3600 * 24 * 3:
                    continue

                # ignore property locations outside of desired regions

                if not region:
                    continue

                while seconds in unsorted_entries:
                    seconds += 1

                unsorted_entries[seconds] = {'region': region, 'price': price, 'bedroom': bedroom, 'area': area, 'title': title, 'url': url, 'id': id}

        entries = {k: unsorted_entries[k] for k in sorted(unsorted_entries)}

        for (seconds, entry) in entries.items():

            region = entry['region']

            region_color = '#000000'
            if region == 1:
                region_color = '#d4540f'
            elif region == 2:
                region_color = '#368718'
            elif region == 3:
                region_color = '#7c1887'
            elif region == 4:
                region_color = '#184c87'
            elif region == 5:
                region_color = '#707070'

            time = ''
            if seconds < 3600:
                time = '< 1 hour'
            else:
                time = '%s hours' % int(seconds / 3600)

            self.index_file.write('<li>')
            if seconds < 3600*24:
                self.index_file.write('* ')
            self.index_file.write('<span style="color: %s;font-weight:bold">[%s]</span> ' % (region_color, region))
            if 'townhouse' in entry['title'].lower() or 'town house' in entry['title'].lower():
                self.index_file.write('<span style="font-weight:bold">')
            else:
                self.index_file.write('<span>')
            self.index_file.write('%s (%sbr %sft) %s ' % (entry['price'], entry['bedroom'], entry['area'], entry['title']))
            self.index_file.write('</span>')
            self.index_file.write('<a href="%s">%s</a>' % (entry['url'], entry['id']))
            self.index_file.write(' [%s]' % time)
            self.index_file.write('</li>')
            self.index_file.write('</br>')

            self.items += 1

    def closed(self, reason):
        self.index_file = open('index.html', 'w')
        self.index_file.write('<head>')
        self.index_file.write('<title>House Search</title>')
        self.index_file.write('<header><h1>House Search</h1></header>')
        self.index_file.write('</head>')
        self.index_file.write('<body>')
        self.index_file.write('<ul>')
        self.index_file.write('<li style="color: #d4540f;font-weight:bold"> Region 1 = UBC / Point Grey / Dunbar </li>')
        self.index_file.write('<li style="color: #368718;font-weight:bold"> Region 2 = Kits / Kerrisdale / South Granville / Mount Pleasant </li>')
        self.index_file.write('<li style="color: #7c1887;font-weight:bold"> Region 3 = Eastside </li>')
        # self.index_file.write('<li style="color: #184c87;font-weight:bold"> Region 4 = North Vancouver </li>')
        # self.index_file.write('<li style="color: #7c1887;font-weight:bold"> Region 5 = West Vancouver </li>')
        # self.index_file.write('<li style="color: #000000;font-weight:bold"> Region 6 = Downtown </li>')
        self.index_file.write('<p></p>')

        self.process_furnished(self.furnished_responses)
        self.process_unfurnished(self.unfurnished_responses)

        self.index_file.write('</ul>')
        self.index_file.write('</body>')
        self.index_file.close()

        print('Processed %s Items' % self.items)
