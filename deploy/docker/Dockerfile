FROM php:8.4-apache
RUN apt-get update && apt-get install -y --no-install-recommends libonig-dev \
    && docker-php-ext-install pdo_mysql mbstring \
    && a2enmod headers rewrite \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/docker/apache.conf /etc/apache2/sites-available/000-default.conf
RUN cp "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"
COPY deploy/docker/php.ini /usr/local/etc/php/conf.d/oddb.ini
COPY app/public /srv/oddb/app/public
COPY app/config /srv/oddb/app/config
RUN find /srv/oddb/app -type d -exec chmod 755 {} + \
    && find /srv/oddb/app -type f -exec chmod 644 {} +
WORKDIR /srv/oddb/app
