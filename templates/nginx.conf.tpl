events {}

pid /tmp/nginx.pid;

http {
    log_format swiftdeploy '$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request';

    access_log /dev/stdout swiftdeploy;
    error_log /dev/stderr warn;

    client_body_temp_path /tmp/client_body_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;

    upstream swiftdeploy_app {
        server app:{{ services.port }};
    }

    server {
        listen {{ nginx.port }};

        add_header X-Deployed-By swiftdeploy always;

        proxy_connect_timeout {{ nginx.proxy_timeout }}s;
        proxy_send_timeout {{ nginx.proxy_timeout }}s;
        proxy_read_timeout {{ nginx.proxy_timeout }}s;

        error_page 502 = @json_502;
        error_page 503 = @json_503;
        error_page 504 = @json_504;

        location / {
            proxy_pass http://swiftdeploy_app;
            proxy_http_version 1.1;

            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            proxy_pass_header X-Mode;
        }

        location @json_502 {
            default_type application/json;
            return 502 '{"error":"bad gateway","code":502,"service":"swiftdeploy","contact":"{{ nginx.contact }}"}';
        }

        location @json_503 {
            default_type application/json;
            return 503 '{"error":"service unavailable","code":503,"service":"swiftdeploy","contact":"{{ nginx.contact }}"}';
        }

        location @json_504 {
            default_type application/json;
            return 504 '{"error":"gateway timeout","code":504,"service":"swiftdeploy","contact":"{{ nginx.contact }}"}';
        }
    }
}
