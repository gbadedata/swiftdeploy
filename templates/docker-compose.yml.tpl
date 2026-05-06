services:
  app:
    image: {{ services.image }}
    container_name: swiftdeploy-app
    restart: {{ services.restart_policy }}
    user: "10001:10001"
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      MODE: "{{ services.mode }}"
      APP_VERSION: "{{ services.version }}"
      APP_PORT: "{{ services.port }}"
    expose:
      - "{{ services.port }}"
    volumes:
      - {{ logs.volume_name }}:/var/log/swiftdeploy
    networks:
      - {{ network.name }}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{{ services.port }}/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s

  nginx:
    image: {{ nginx.image }}
    container_name: swiftdeploy-nginx
    restart: {{ services.restart_policy }}
    user: "101:101"
    depends_on:
      app:
        condition: service_healthy
    ports:
      - "{{ nginx.port }}:{{ nginx.port }}"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - {{ logs.volume_name }}:/var/log/nginx
    networks:
      - {{ network.name }}
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{{ nginx.port }}/healthz"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s

  opa:
    image: {{ opa.image }}
    container_name: swiftdeploy-opa
    restart: {{ services.restart_policy }}
    command:
      - "run"
      - "--server"
      - "--addr=0.0.0.0:{{ opa.port }}"
      - "/policies"
    ports:
      - "127.0.0.1:{{ opa.port }}:{{ opa.port }}"
    volumes:
      - ./{{ opa.policies_dir }}:/policies:ro
    networks:
      - {{ network.name }}
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test: ["CMD", "/opa", "eval", "true"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 5s

networks:
  {{ network.name }}:
    driver: {{ network.driver_type }}

volumes:
  {{ logs.volume_name }}:
