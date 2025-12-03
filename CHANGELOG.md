# Changelog

## [2.2.1](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v2.2.0...v2.2.1) (2025-12-03)


### Bug Fixes

* revert changes made to logging statements ([2edbea9](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/2edbea90af59d5ef028fb7069cbb3eabfd477f62))

## [2.2.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v2.1.0...v2.2.0) (2025-12-03)


### Features

* add parallel processing for requests ([aa469f4](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/aa469f4f28e96f04e589100ca2b2c0d6e3b7dea6))

## [2.1.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v2.0.0...v2.1.0) (2025-12-01)


### Features

* add env variable to clear cache on startup ([c2f3bfd](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/c2f3bfdd7484e87f732ca85763c64646927d2839))


### Bug Fixes

* always update metrics even if cache is not changed ([06145ef](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/06145ef2b9ae03c30cebacb0429414398366adaf))

## [2.0.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.3.0...v2.0.0) (2025-11-26)


### ⚠ BREAKING CHANGES

* Existing dashboards, alerts, and queries checking for == -1 will need to be updated to check for == 0. The statuspage_service_status and statuspage_component_status metrics now use 0 for degraded/incident states instead of -1.

### Features

* Change status values from 1/-1 to 1/0 for binary logic ([90c91ac](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/90c91accee64715e63df93a3d1a9ccb6c9ca1540))

## [1.3.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.2.2...v1.3.0) (2025-11-25)


### Features

* add component timestamp, probe check, and application timestamp gauges ([e2fbb66](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/e2fbb66ead98ba75009a9a0d4296a593beac9229))

## [1.2.2](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.2.1...v1.2.2) (2025-11-24)


### Bug Fixes

* remove doc copy steps in docker build ([8339716](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/833971655d79d8264244d92b6ab191bd1756b79a))

## [1.2.1](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.2.0...v1.2.1) (2025-11-24)


### Bug Fixes

* correct component status mapping for StatusPage.io API ([760143a](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/760143af38d946ce9c41f63e34b455f94631cb9d))
* remove maintenance from StatusPage.io top-level status indicator ([a39f8c3](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/a39f8c3a9f0e7309973480f7c2d8c33fd8598f68))

## [1.2.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.1.1...v1.2.0) (2025-11-22)


### Features

* add DEBUG environment variable for configurable logging level ([d4e3749](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/d4e3749074e6240ae25d648f10b966d2bdd97cea))

## [1.1.1](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.1.0...v1.1.1) (2025-11-21)


### Bug Fixes

* release note workflow to publish to docker hub ([2ae442e](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/2ae442e3b269dc4ced60740ec9d98461216a4a2a))

## [1.1.0](https://github.com/mcarvin8/statuspage-prometheus-exporter/compare/v1.0.0...v1.1.0) (2025-11-21)


### Features

* add configurable check interval env variable ([5b0fd6a](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/5b0fd6a9d418c6e64b3a0094aa6f6796195c03ff))

## 1.0.0 (2025-11-21)


### Features

* add chili piper and qualified to services.json ([4c6ef02](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/4c6ef0263faaffe4ab757dd65a6163d91a34a70d))
* add component monitoring and ensure timestamps are normalized ([54c909c](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/54c909cd3a3dd706c7033576325586f32b1e912d))
* add gainsight and leandata urls ([b850cbf](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/b850cbf3fcc7e1c3c31c58e629020f91cc225402))
* add more services ([459f535](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/459f5357b9c5d40baaf275f7183e6bef41e56cad))
* add outreach html monitoring service ([279a417](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/279a417560befb45c5fe5ef8c8fb37a24c2eebd5))
* create cache manager for outreach service ([6dd66e4](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/6dd66e4e3e96b3a39344b4a392009cc76207637b))
* create cache manager for primary service ([d2fd5e2](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/d2fd5e2b037e74e2d2d42da99ef8a6b95ace2138))
* create sample prometheus rule manifest ([4a4dbc0](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/4a4dbc04f9d4858bdf87b5369a5d0c213fb5ce90))
* grafana dashboard updates for component row ([9996652](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/9996652a6abc5eb93ae8fe0203ea9415f0cc4b6d))
* include docker publish job ([34093fa](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/34093fa1e32d371d6a8aff33104449a566cfbc05))
* init commit ([94cad04](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/94cad046b64f2dc4631d3d5c8f9adf68c09ef5e0))


### Bug Fixes

* chili piper link ([0edfdc6](https://github.com/mcarvin8/statuspage-prometheus-exporter/commit/0edfdc694217349dfcfa6f1c9cc25f22d316278f))
