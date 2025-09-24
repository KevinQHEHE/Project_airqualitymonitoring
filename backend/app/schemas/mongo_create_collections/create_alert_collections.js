// Helper script to create alert_subscriptions and notification_logs collections
// Run with: mongo <uri>/<db> create_alert_collections.js

const subsValidator = cat('schemas/mongo_validators/alert_subscriptions.validator.json');
const logsValidator = cat('schemas/mongo_validators/notification_logs.validator.json');

// Create or update alert_subscriptions
try {
  db.createCollection('alert_subscriptions', { validator: subsValidator, validationLevel: 'moderate' });
  print('Created alert_subscriptions collection');
} catch (e) {
  print('alert_subscriptions exists or failed to create: ' + e);
}

// Create or update notification_logs
try {
  db.createCollection('notification_logs', { validator: logsValidator, validationLevel: 'moderate' });
  print('Created notification_logs collection');
} catch (e) {
  print('notification_logs exists or failed to create: ' + e);
}

// Ensure indexes for alert_subscriptions
try {
  db.alert_subscriptions.createIndex({ user_id: 1 });
  db.alert_subscriptions.createIndex({ station_id: 1 });
  // composite for querying subscriptions by station and threshold (e.g., find subscriptions where threshold <= current aqi)
  db.alert_subscriptions.createIndex({ station_id: 1, alert_threshold: 1, status: 1 });
  // ensure quick lookup by user and status
  db.alert_subscriptions.createIndex({ user_id: 1, status: 1 });
  print('Indexes created for alert_subscriptions');
} catch (e) {
  print('Failed creating indexes on alert_subscriptions: ' + e);
}

// Ensure indexes for notification_logs
try {
  db.notification_logs.createIndex({ subscription_id: 1 });
  db.notification_logs.createIndex({ user_id: 1 });
  db.notification_logs.createIndex({ station_id: 1 });
  db.notification_logs.createIndex({ sentAt: 1 });
  // TTL for retention policy: keep logs for 90 days
  const ninetyDaysSeconds = 90 * 24 * 60 * 60;
  try {
    db.notification_logs.createIndex({ sentAt: 1 }, { expireAfterSeconds: ninetyDaysSeconds });
  } catch (e) {
    print('Could not create TTL index on notification_logs.sentAt: ' + e);
  }
  print('Indexes created for notification_logs (including TTL)');
} catch (e) {
  print('Failed creating indexes on notification_logs: ' + e);
}
