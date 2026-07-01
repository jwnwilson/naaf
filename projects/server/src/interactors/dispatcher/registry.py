from interactors.dispatcher.subscriber import EventSubscriber
from interactors.dispatcher.subscribers.notifications import NotificationSubscriber

SUBSCRIBERS: list[EventSubscriber] = [NotificationSubscriber()]
